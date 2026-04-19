import json


def build_lawyer_triples(case_data):
    triples = []
    case_node = f"Case::{case_data['case_id']}"
    plaintiff = case_data.get("plaintiff")
    defendant = case_data.get("defendant")
    lawyers = case_data.get("lawyers", [])

    for lawyer in lawyers:
        lawyer_name = lawyer.get("name")
        lawyer_role = lawyer.get("role")

        if not lawyer_name:
            continue

        lawyer_node = f"Lawyer::{lawyer_name}"
        role_node = f"LawyerRole::{lawyer_role}"

        # 案件有這位律師
        triples.append((case_node, "HAS_LAWYER", lawyer_node))

        # 律師在案件中的角色
        triples.append((lawyer_node, "HAS_ROLE", role_node))
        triples.append((lawyer_node, "ACTS_IN", case_node))

        # 如果能判斷代表誰，就連回當事人
        if "原告" in lawyer_role and plaintiff:
            party_node = f"Party::{plaintiff}"
            triples.append((party_node, "REPRESENTED_BY", lawyer_node))
            triples.append((lawyer_node, "REPRESENTS", party_node))

        elif "被告" in lawyer_role and defendant:
            party_node = f"Party::{defendant}"
            triples.append((party_node, "REPRESENTED_BY", lawyer_node))
            triples.append((lawyer_node, "REPRESENTS", party_node))

    return triples


def build_triples(case_data):
    triples = []
    case_node = f"Case::{case_data['case_id']}"

    if case_data.get("court"):
        triples.append((case_node, "HEARD_BY", f"Court::{case_data['court']}"))

    if case_data.get("cause"):
        triples.append((case_node, "HAS_CAUSE", f"Cause::{case_data['cause']}"))

    if case_data.get("plaintiff"):
        triples.append((case_node, "HAS_PLAINTIFF", f"Party::{case_data['plaintiff']}"))

    if case_data.get("defendant"):
        triples.append((case_node, "HAS_DEFENDANT", f"Party::{case_data['defendant']}"))

    if case_data.get("judge"):
        triples.append((case_node, "JUDGED_BY", f"Judge::{case_data['judge']}"))

    if case_data.get("clerk"):
        triples.append((case_node, "RECORDED_BY", f"Clerk::{case_data['clerk']}"))

    for article in case_data.get("articles", []):
        triples.append((case_node, "CITES_ARTICLE", f"LawArticle::{article}"))

    decision_node = f"Decision::{case_data['case_id']}"
    if case_data.get("decision_type"):
        triples.append((case_node, "HAS_DECISION", decision_node))
        triples.append((decision_node, "DECISION_TYPE", f"DecisionType::{case_data['decision_type']}"))

    for amount in case_data.get("money", []):
        triples.append((decision_node, "REQUIRES_PAYMENT", f"Money::{amount}元"))

    triples.extend(build_lawyer_triples(case_data))

    return triples


if __name__ == "__main__":
    with open("data/processed_cases.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    all_triples = []
    for item in data:
        all_triples.extend(build_triples(item))

    with open("output/case_triples.json", "w", encoding="utf-8") as f:
        json.dump(all_triples, f, ensure_ascii=False, indent=2)

    print("triples 建立完成，輸出到 output/case_triples.json")