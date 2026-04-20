import json
from neo4j import GraphDatabase

URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "hudson0306"   # 這裡改成你自己的 Neo4j 密碼

driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))


def parse_node(node_str):
    label, name = node_str.split("::", 1)
    return label, name


def merge_node_and_relation(tx, s, p, o):
    s_label, s_name = parse_node(s)
    o_label, o_name = parse_node(o)

    query = f"""
    MERGE (a:{s_label} {{name: $s_name}})
    MERGE (b:{o_label} {{name: $o_name}})
    MERGE (a)-[:{p}]->(b)
    """
    tx.run(query, s_name=s_name, o_name=o_name)


if __name__ == "__main__":
    with open("output/case_triples_v2.json", "r", encoding="utf-8") as f:
        triples = json.load(f)

    with driver.session() as session:
        for s, p, o in triples:
            session.execute_write(merge_node_and_relation, s, p, o)

    driver.close()
    print("成功上傳到 Neo4j")