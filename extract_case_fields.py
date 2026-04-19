import re
import json


def normalize_text(text: str) -> str:
    text = text.replace("\u3000", " ")
    text = text.replace("臺", "台")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def extract_court(text: str):
    patterns = [
        r"(台灣[\w]+地方法院)",
        r"(台灣[\w]+高等法院)",
        r"(最高法院)"
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(1)
    return None


def extract_case_number(text: str):
    m = re.search(r"(\d+\s*年度[\w]+字第\s*\d+\s*號)", text)
    if m:
        return re.sub(r"\s+", "", m.group(1))
    return None


def extract_judgment_date(text: str):
    m = re.search(r"裁判日期：\s*民國\s*(\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日", text)
    if m:
        year, month, day = m.groups()
        return f"民國{year}年{month}月{day}日"
    return None


def extract_case_cause(text: str):
    m = re.search(r"裁判案由：\s*([^\n]+)", text)
    return m.group(1).strip() if m else None


def extract_plaintiff(text: str):
    m = re.search(r"原\s*告\s+([^\n\s]+)", text)
    return m.group(1).strip() if m else None


def extract_defendant(text: str):
    m = re.search(r"被告([^\s間\n]+)", text)
    return m.group(1).strip() if m else None


def extract_judge(text: str):
    m = re.search(r"法\s*官\s*([^\s\n]+)", text)
    return m.group(1).strip() if m else None


def extract_clerk(text: str):
    m = re.search(r"書記官\s*([^\s\n]+)", text)
    return m.group(1).strip() if m else None


def extract_main_text(text: str):
    m = re.search(r"主\s*文(.*?)理\s*由", text, re.S)
    if m:
        return m.group(1).strip()
    return None


def extract_reason_text(text: str):
    m = re.search(r"理\s*由(.*)", text, re.S)
    if m:
        return m.group(1).strip()
    return None


def extract_money(text: str):
    patterns = [
        r"新台幣\s*([\d,]+)\s*元",
        r"新臺幣\s*([\d,]+)\s*元"
    ]
    results = []
    for p in patterns:
        for match in re.findall(p, text):
            results.append(match.replace(",", ""))
    return list(set(results))


def extract_articles(text: str):
    laws = ["家事事件法", "民事訴訟法", "非訟事件法", "民法", "刑法", "刑事訴訟法"]
    found = []

    for law in laws:
        pattern = rf"{law}第\d+條(?:之\d+)?(?:第\d+項)?"
        matches = re.findall(pattern, text)
        found.extend(matches)

        grouped_pattern = rf"{law}第\d+條(?:之\d+)?(?:第\d+項)?(?:、第\d+條(?:之\d+)?(?:第\d+項)?)+"
        grouped_matches = re.findall(grouped_pattern, text)
        for gm in grouped_matches:
            first = re.match(rf"({law})第(\d+條(?:之\d+)?(?:第\d+項)?)", gm)
            if first:
                law_name = first.group(1)
                first_article = first.group(2)
                found.append(f"{law_name}第{first_article}")

                others = re.findall(r"第(\d+條(?:之\d+)?(?:第\d+項)?)", gm[len(f'{law_name}第{first_article}'):])
                for article in others:
                    found.append(f"{law_name}第{article}")

    return sorted(list(set(found)))


def extract_decision_type(main_text: str):
    if not main_text:
        return None
    if "駁回" in main_text:
        return "駁回"
    if "准許" in main_text:
        return "准許"
    if "應於" in main_text and "繳納" in main_text:
        return "命補裁判費"
    return "其他"


def extract_lawyers(text: str):
    """
    抽取律師資訊，回傳：
    [
      {
        "name": "王小明律師",
        "role": "原告訴訟代理人"
      }
    ]
    """
    patterns = [
        (r"原告訴訟代理人\s*([^\s\n]+律師)", "原告訴訟代理人"),
        (r"被告訴訟代理人\s*([^\s\n]+律師)", "被告訴訟代理人"),
        (r"訴訟代理人\s*([^\s\n]+律師)", "訴訟代理人"),
        (r"選任辯護人\s*([^\s\n]+律師)", "選任辯護人"),
        (r"辯護人\s*([^\s\n]+律師)", "辯護人"),
        (r"代理人\s*([^\s\n]+律師)", "代理人")
    ]

    lawyers = []
    for pattern, role in patterns:
        matches = re.findall(pattern, text)
        for m in matches:
            lawyers.append({
                "name": m.strip(),
                "role": role
            })

    unique = []
    seen = set()
    for item in lawyers:
        key = (item["name"], item["role"])
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


def process_case(record):
    raw_text = record.get("case_content", "")
    text = normalize_text(raw_text)

    main_text = extract_main_text(text)
    reason_text = extract_reason_text(text)

    return {
        "case_id": record.get("case_id"),
        "court": extract_court(text),
        "case_number": extract_case_number(text),
        "judgment_date": extract_judgment_date(text),
        "cause": extract_case_cause(text),
        "plaintiff": extract_plaintiff(text),
        "defendant": extract_defendant(text),
        "judge": extract_judge(text),
        "clerk": extract_clerk(text),
        "main_text": main_text,
        "reason_text": reason_text,
        "articles": extract_articles(text),
        "money": extract_money(text),
        "decision_type": extract_decision_type(main_text),
        "lawyers": extract_lawyers(text),
        "raw_text": text
    }


if __name__ == "__main__":
    with open("jud_data.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    processed = [process_case(x) for x in data]

    with open("data/processed_cases.json", "w", encoding="utf-8") as f:
        json.dump(processed, f, ensure_ascii=False, indent=2)

    print("欄位抽取完成，輸出到 data/processed_cases.json")