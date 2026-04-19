import json
import re
from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "hudson0306"

PROCESSED_JSON = "data/processed_cases.json"
OPENIE_JSON = "output/openie_triples.json"

driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))


def is_money(text: str) -> bool:
    return bool(re.search(r"\d[\d,]*元|[壹貳參肆伍陸柒捌玖拾佰仟萬貳]+元", text))


def is_time(text: str) -> bool:
    keywords = ["日內", "月內", "年內", "日起", "貳月", "參月", "壹月", "月", "日", "自民國"]
    return any(k in text for k in keywords)


def is_law_article(text: str) -> bool:
    return ("法第" in text) or ("條例第" in text)


def is_person_name(text: str) -> bool:
    if not text:
        return False
    bad = ["本件", "原告", "被告", "裁判費", "主文", "理由", "禁止接見通信", "程序", "費用"]
    if any(b in text for b in bad):
        return False
    if len(text) > 80:
        return False
    return True


def normalize_relation(relation: str) -> str:
    mapping = {
        "羈押": "EXTENDS_DETENTION",
        "延長羈押": "EXTENDS_DETENTION",
        "解除禁止接見通信": "LIFTS_RESTRICTION",
        "請求": "REQUESTS",
        "金額為": "HAS_AMOUNT",
        "應繳納": "REQUIRES_PAYMENT",
        "應徵收裁判費": "REQUIRES_PAYMENT",
        "引用法條": "CITES_ARTICLE",
        "適用於": "CITES_ARTICLE",
    }
    return mapping.get(relation, relation)


def merge_case_backbone(tx, case_data):
    case_id = case_data.get("case_id")
    case_type = case_data.get("case_type")
    court = case_data.get("court")
    cause = case_data.get("cause")
    judge = case_data.get("judge")
    plaintiff = case_data.get("plaintiff")
    defendant = case_data.get("defendant")
    lawyers = case_data.get("lawyers", [])
    articles = case_data.get("articles", [])

    tx.run("MERGE (c:Case {name:$case_id})", case_id=case_id)

    if case_type:
        tx.run("""
            MERGE (c:Case {name:$case_id})
            MERGE (ct:CaseType {name:$case_type})
            MERGE (c)-[:HAS_CASE_TYPE]->(ct)
        """, case_id=case_id, case_type=case_type)

    if court:
        tx.run("""
            MERGE (c:Case {name:$case_id})
            MERGE (co:Court {name:$court})
            MERGE (c)-[:HEARD_BY]->(co)
        """, case_id=case_id, court=court)

    if cause:
        tx.run("""
            MERGE (c:Case {name:$case_id})
            MERGE (ca:Cause {name:$cause})
            MERGE (c)-[:HAS_CAUSE]->(ca)
        """, case_id=case_id, cause=cause)

    if judge:
        tx.run("""
            MERGE (c:Case {name:$case_id})
            MERGE (j:Judge {name:$judge})
            MERGE (c)-[:JUDGED_BY]->(j)
        """, case_id=case_id, judge=judge)

    if plaintiff:
        tx.run("""
            MERGE (c:Case {name:$case_id})
            MERGE (p:Litigant {name:$plaintiff})
            MERGE (c)-[:HAS_PLAINTIFF]->(p)
        """, case_id=case_id, plaintiff=plaintiff)

    if defendant:
        tx.run("""
            MERGE (c:Case {name:$case_id})
            MERGE (d:Litigant {name:$defendant})
            MERGE (c)-[:HAS_DEFENDANT]->(d)
        """, case_id=case_id, defendant=defendant)

    for lawyer in lawyers:
        lawyer_name = lawyer.get("name")
        lawyer_role = lawyer.get("role")
        if not lawyer_name:
            continue

        tx.run("""
            MERGE (c:Case {name:$case_id})
            MERGE (l:Lawyer {name:$lawyer_name})
            MERGE (c)-[:HAS_LAWYER]->(l)
        """, case_id=case_id, lawyer_name=lawyer_name)

        if lawyer_role:
            tx.run("""
                MERGE (l:Lawyer {name:$lawyer_name})
                MERGE (r:LawyerRole {name:$lawyer_role})
                MERGE (l)-[:HAS_ROLE]->(r)
            """, lawyer_name=lawyer_name, lawyer_role=lawyer_role)

    for article in articles:
        tx.run("""
            MERGE (c:Case {name:$case_id})
            MERGE (a:LawArticle {name:$article})
            MERGE (c)-[:CITES_ARTICLE]->(a)
        """, case_id=case_id, article=article)


def merge_openie_formal(tx, case_id, triple):
    subject = str(triple.get("subject", "")).strip()
    relation = str(triple.get("relation", "")).strip()
    obj = str(triple.get("object", "")).strip()

    if not subject or not relation or not obj:
        return

    rel = normalize_relation(relation)

    tx.run("MERGE (c:Case {name:$case_id})", case_id=case_id)

    if is_person_name(subject):
        tx.run("""
            MERGE (c:Case {name:$case_id})
            MERGE (p:Litigant {name:$subject})
            MERGE (c)-[:HAS_DEFENDANT]->(p)
        """, case_id=case_id, subject=subject)

    if rel == "CITES_ARTICLE" and is_law_article(obj):
        tx.run("""
            MERGE (c:Case {name:$case_id})
            MERGE (a:LawArticle {name:$obj})
            MERGE (c)-[:CITES_ARTICLE]->(a)
        """, case_id=case_id, obj=obj)
        return

    if rel == "EXTENDS_DETENTION":
        tx.run("""
            MERGE (c:Case {name:$case_id})
            MERGE (p:Litigant {name:$subject})
            MERGE (dt:DecisionType {name:"延長羈押"})
            MERGE (act:Action {name:"延長羈押"})
            MERGE (tm:Time {name:$obj})
            MERGE (c)-[:HAS_DEFENDANT]->(p)
            MERGE (c)-[:HAS_DECISION_TYPE]->(dt)
            MERGE (c)-[:EXTENDS_DETENTION]->(act)
            MERGE (act)-[:HAS_DURATION]->(tm)
        """, case_id=case_id, subject=subject, obj=obj)
        return

    if rel == "LIFTS_RESTRICTION":
        tx.run("""
            MERGE (c:Case {name:$case_id})
            MERGE (p:Litigant {name:$subject})
            MERGE (act:Action {name:"解除禁止接見通信"})
            MERGE (tm:Time {name:$obj})
            MERGE (c)-[:HAS_DEFENDANT]->(p)
            MERGE (c)-[:LIFTS_RESTRICTION]->(act)
            MERGE (act)-[:AT_TIME]->(tm)
        """, case_id=case_id, subject=subject, obj=obj)
        return

    if rel in ["HAS_AMOUNT", "REQUIRES_PAYMENT"] and is_money(obj):
        tx.run("""
            MERGE (c:Case {name:$case_id})
            MERGE (m:Money {name:$obj})
            MERGE (c)-[:REQUIRES_PAYMENT]->(m)
        """, case_id=case_id, obj=obj)
        return

    if rel == "REQUESTS":
        tx.run("""
            MERGE (c:Case {name:$case_id})
            MERGE (p:Litigant {name:$subject})
            MERGE (act:Action {name:$obj})
            MERGE (c)-[:HAS_PLAINTIFF]->(p)
            MERGE (p)-[:REQUESTS]->(act)
        """, case_id=case_id, subject=subject, obj=obj)
        return


def main():
    with open(PROCESSED_JSON, "r", encoding="utf-8") as f:
        processed_cases = json.load(f)

    with open(OPENIE_JSON, "r", encoding="utf-8") as f:
        openie_cases = json.load(f)

    processed_map = {x["case_id"]: x for x in processed_cases}

    with driver.session() as session:
        # 先建骨架
        for case_id, case_data in processed_map.items():
            session.execute_write(merge_case_backbone, case_data)

        # 再把 OpenIE 映射進正式 KG
        for case in openie_cases:
            case_id = case.get("case_id", "").strip()
            for chunk in case.get("chunks", []):
                for triple in chunk.get("triples", []):
                    session.execute_write(merge_openie_formal, case_id, triple)

    driver.close()
    print("完整正式 KG 上傳完成")
    

if __name__ == "__main__":
    main()