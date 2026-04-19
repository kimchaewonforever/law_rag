import re
import json
import time
import requests
from typing import List, Dict, Any

INPUT_JSON = "jud_data.json"
OUTPUT_JSON = "output/openie_triples.json"

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:7b"

SLEEP_SECONDS = 1


def normalize_text(text: str) -> str:
    text = text.replace("\u3000", " ")
    text = text.replace("臺", "台")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def extract_case_type(text: str) -> str:
    if "刑事判決" in text or "刑事裁定" in text:
        return "刑事"
    if "民事判決" in text or "民事裁定" in text:
        return "民事"
    if "家事" in text:
        return "民事"
    return "其他"


def split_case_content(text: str) -> List[Dict[str, str]]:
    sections = []
    text = normalize_text(text)

    patterns = [
        ("基本資訊", r"(裁判字號：.*?)(?=主\s*文|理\s*由|$)"),
        ("主文", r"(主\s*文.*?)(?=理\s*由|$)"),
        ("理由", r"(理\s*由.*)")
    ]

    for name, pattern in patterns:
        m = re.search(pattern, text, re.S)
        if m:
            content = m.group(1).strip()
            if content:
                sections.append({
                    "section": name,
                    "content": content
                })

    if not sections:
        sections.append({
            "section": "全文",
            "content": text
        })

    return sections


def get_openie_prompt(case_type: str, chunk_text: str) -> str:
    common_rules = """
你是一個法律知識圖譜建構系統。
請從以下法院裁判文本中抽取知識圖譜三元組。

【共通規則】
1. 僅根據文本內容抽取，不可加入外部知識。
2. 只抽取法律上有意義的三元組，不要抽太瑣碎的文字。
3. subject、relation、object 要簡短明確。
4. 若同一句可拆成多個有意義的三元組，請拆開。
5. 法條名稱盡量完整保留，例如「刑事訴訟法第101條第1項」。
6. 若資訊不足，請略過，不要猜測。
7. 不要輸出重複三元組。
8. 嚴格輸出 JSON，不要加任何說明文字。
9. 只輸出一個 JSON 物件。

【輸出格式】
{
  "triples": [
    {
      "subject": "...",
      "relation": "...",
      "object": "...",
      "evidence": "..."
    }
  ]
}
"""

    if case_type == "刑事":
        task = """
【刑事案件抽取重點】
請優先抽取與以下資訊有關的三元組：
- 被告
- 辯護人 / 選任辯護人 / 公設辯護人
- 罪名 / 犯罪行為
- 引用法條
- 裁判結果
- 刑度 / 羈押 / 交保 / 限制住居
- 法官
- 法院

【建議關係】
- 被告
- 辯護人
- 選任辯護人
- 代理
- 涉犯
- 引用法條
- 裁判結果
- 判處
- 羈押
- 交保
- 限制住居
- 審理法院
- 法官
"""
    else:
        task = """
【民事案件抽取重點】
請優先抽取與以下資訊有關的三元組：
- 原告
- 被告
- 訴訟代理人
- 請求事項
- 裁判結果
- 引用法條
- 裁判費 / 金額
- 期限
- 法官
- 法院

【建議關係】
- 原告
- 被告
- 訴訟代理人
- 代表
- 請求
- 引用法條
- 裁判結果
- 命補繳
- 金額為
- 應於
- 逾期未補正即
- 審理法院
- 法官
"""

    return f"""{common_rules}

{task}

【文本】
{chunk_text}
"""


def extract_json_block(text: str) -> Dict[str, Any]:
    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    m = re.search(r"\{.*\}", text, re.S)
    if m:
        block = m.group(0)
        try:
            return json.loads(block)
        except Exception:
            pass

    return {"triples": []}


def call_ollama(prompt: str) -> Dict[str, Any]:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0
        }
    }

    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=600)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("response", "").strip()
        return extract_json_block(content)
    except Exception as e:
        print(f"[Ollama 呼叫失敗] {e}")
        return {"triples": []}


def clean_triples(triples: List[Dict[str, str]]) -> List[Dict[str, str]]:
    cleaned = []
    seen = set()

    for t in triples:
        s = str(t.get("subject", "")).strip()
        r = str(t.get("relation", "")).strip()
        o = str(t.get("object", "")).strip()
        e = str(t.get("evidence", "")).strip()

        if not s or not r or not o:
            continue

        key = (s, r, o)
        if key in seen:
            continue
        seen.add(key)

        cleaned.append({
            "subject": s,
            "relation": r,
            "object": o,
            "evidence": e
        })

    return cleaned


def process_case(record: Dict[str, Any]) -> Dict[str, Any]:
    case_id = record.get("case_id", "").strip()
    case_content = normalize_text(record.get("case_content", ""))
    case_type = record.get("case_type") or extract_case_type(case_content)

    sections = split_case_content(case_content)

    case_result = {
        "case_id": case_id,
        "case_type": case_type,
        "chunks": []
    }

    for sec in sections:
        prompt = get_openie_prompt(case_type, sec["content"])
        llm_result = call_ollama(prompt)
        triples = clean_triples(llm_result.get("triples", []))

        case_result["chunks"].append({
            "section": sec["section"],
            "text": sec["content"],
            "triples": triples
        })

        time.sleep(SLEEP_SECONDS)

    return case_result


def main():
    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    data = data[:3]
    all_results = []
    total = len(data)

    for idx, record in enumerate(data, start=1):
        case_id = record.get("case_id", f"case_{idx}")
        print(f"[{idx}/{total}] 處理中：{case_id}")
        result = process_case(record)
        all_results.append(result)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"完成，輸出到 {OUTPUT_JSON}")


if __name__ == "__main__":
    main()