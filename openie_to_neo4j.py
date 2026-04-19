import json
from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "hudson0306"

OPENIE_JSON = "output/openie_triples.json"

driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))


def merge_openie_triple(tx, case_id, case_type, section, triple):
    subject = str(triple.get("subject", "")).strip()
    relation = str(triple.get("relation", "")).strip()
    obj = str(triple.get("object", "")).strip()
    evidence = str(triple.get("evidence", "")).strip()

    if not subject or not relation or not obj:
        return

    query = """
    MERGE (c:Case {name: $case_id})
      ON CREATE SET c.case_type = $case_type

    MERGE (sec:Section {name: $section})

    MERGE (s:OpenEntity {name: $subject})
    MERGE (o:OpenEntity {name: $object})

    MERGE (t:OpenTriple {
        case_id: $case_id,
        section: $section,
        subject: $subject,
        relation: $relation,
        object: $object
    })
    SET t.evidence = $evidence,
        t.case_type = $case_type

    MERGE (c)-[:HAS_OPENIE_TRIPLE]->(t)
    MERGE (t)-[:HAS_SUBJECT]->(s)
    MERGE (t)-[:HAS_OBJECT]->(o)
    MERGE (t)-[:IN_SECTION]->(sec)
    """

    tx.run(
        query,
        case_id=case_id,
        case_type=case_type,
        section=section,
        subject=subject,
        relation=relation,
        object=obj,
        evidence=evidence
    )


def main():
    with open(OPENIE_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    with driver.session() as session:
        for case in data:
            case_id = case.get("case_id", "").strip()
            case_type = case.get("case_type", "").strip()

            for chunk in case.get("chunks", []):
                section = chunk.get("section", "").strip()
                triples = chunk.get("triples", [])

                for triple in triples:
                    session.execute_write(
                        merge_openie_triple,
                        case_id,
                        case_type,
                        section,
                        triple
                    )

    driver.close()
    print("OpenIE 結果成功上傳到 Neo4j")


if __name__ == "__main__":
    main()