import json
import os
import re
import time
from typing import Any, Dict, List, Optional

import requests

INPUT_JSON = "jud_data.json"
OUTPUT_JSON = "output/openie_triples_v2.json"

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:7b"  
REQUEST_TIMEOUT = 720        
SLEEP_SECONDS = 1              
MAX_CASES = 20
SKIP_DONE = True                


def preprocess_legal_text(text: str) -> str:
    text = text.replace("\u3000", " ")
    text = text.replace("臺", "台")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    cleaned_lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    replacements = {
        r"原\s*告": "原告",
        r"被\s*告": "被告",
        r"公\s*訴\s*人": "公訴人",
        r"聲\s*請\s*人": "聲請人",
        r"相\s*對\s*人": "相對人",
        r"關\s*係\s*人": "關係人",
        r"被\s*繼\s*承\s*人": "被繼承人",
        r"選\s*任\s*辯\s*護\s*人": "選任辯護人",
        r"公\s*設\s*辯\s*護\s*人": "公設辯護人",
        r"辯\s*護\s*人": "辯護人",
        r"訴\s*訟\s*代\s*理\s*人": "訴訟代理人",
        r"代\s*理\s*人": "代理人",
        r"法\s*官": "法官",
        r"書\s*記\s*官": "書記官",
        r"主\s*文": "主文",
        r"理\s*由": "理由",
        r"裁\s*判\s*字\s*號": "裁判字號",
        r"裁\s*判\s*日\s*期": "裁判日期",
        r"裁\s*判\s*案\s*由": "裁判案由",
    }

    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)

    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_case_type(text: str) -> str:
    if "刑事判決" in text or "刑事裁定" in text:
        return "刑事"
    if "民事判決" in text or "民事裁定" in text:
        return "民事"
    if "家事" in text:
        return "家事"
    return "其他"


def extract_main_text(text: str) -> str:
    text = preprocess_legal_text(text)

    m = re.search(r"主文(.*?)(?=理由|$)", text, re.S)
    if m:
        main_text = m.group(1).strip()
        # 主文太長就切短，先求穩
        return main_text[:600]

    return text[:600]


def get_openie_prompt(case_type: str, main_text: str) -> str:
    common = """
你是法律資訊抽取系統。
請只根據提供的主文內容，抽取重要三元組。
不要猜測，不要補充文本沒有的資訊。
只輸出 JSON，不要輸出任何說明。

輸出格式：
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
        focus = """
抽取重點：
- 被告
- 羈押 / 延長羈押
- 解除限制
- 駁回聲請
- 具保 / 停止羈押
- 期間
- 律師
- 法官
"""
    else:
        focus = """
抽取重點：
- 原告 / 被告 / 聲請人 / 相對人
- 請求
- 駁回 / 准許
- 裁判費 / 金額
- 命補繳
- 期限
- 律師
- 法官
"""

    return f"""{common}
{focus}

主文：
{main_text}
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

    resp = requests.post(OLLAMA_URL, json=payload, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    content = data.get("response", "").strip()
    return extract_json_block(content)


def clean_triples(triples: List[Dict[str, Any]]) -> List[Dict[str, str]]:
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


def load_existing_results() -> List[Dict[str, Any]]:
    if not os.path.exists(OUTPUT_JSON):
        return []

    try:
        with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_results(results: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def process_case(record: Dict[str, Any]) -> Dict[str, Any]:
    case_id = record.get("case_id", "").strip()
    raw_text = record.get("case_content", "")
    clean_text = preprocess_legal_text(raw_text)
    case_type = record.get("case_type") or extract_case_type(clean_text)
    main_text = extract_main_text(clean_text)

    prompt = get_openie_prompt(case_type, main_text)

    try:
        llm_result = call_ollama(prompt)
        triples = clean_triples(llm_result.get("triples", []))
        status = "success"
        error = None
    except Exception as e:
        triples = []
        status = "error"
        error = str(e)

    return {
        "case_id": case_id,
        "case_type": case_type,
        "chunks": [
            {
                "section": "主文",
                "text": main_text,
                "triples": triples
            }
        ],
        "status": status,
        "error": error
    }


def main():
    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    if MAX_CASES is not None:
        data = data[:MAX_CASES]

    existing_results = load_existing_results()
    done_case_ids = {x.get("case_id") for x in existing_results}

    results = existing_results[:]
    total = len(data)

    for idx, record in enumerate(data, start=1):
        case_id = record.get("case_id", f"case_{idx}")

        if SKIP_DONE and case_id in done_case_ids:
            print(f"[{idx}/{total}] 跳過已完成：{case_id}")
            continue

        print(f"[{idx}/{total}] 處理中：{case_id}")

        case_result = process_case(record)
        results.append(case_result)
        save_results(results)

        print(
            f"  -> status={case_result['status']}, "
            f"triples={len(case_result['chunks'][0]['triples'])}"
        )

        time.sleep(SLEEP_SECONDS)

    print(f"完成，輸出到 {OUTPUT_JSON}")


if __name__ == "__main__":
    main()