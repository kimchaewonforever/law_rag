import re
import json

def preprocess_legal_text(text: str) -> str:
    # 1. 統一字元
    text = text.replace("\u3000", " ")
    text = text.replace("臺", "台")

    # 2. 統一換行
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 3. 壓縮每行內多餘空白
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        lines.append(line)

    text = "\n".join(lines)

    # 4. 關鍵欄位名稱內部空白修正
    replacements = {
        r"原\s*告": "原告",
        r"被\s*告": "被告",
        r"公\s*訴\s*人": "公訴人",
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

    # 5. 多餘空行壓縮
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()
def split_legal_sections(text: str):
    text = preprocess_legal_text(text)

    header = ""
    main_text = ""
    reason = ""
    footer = ""

    m_header = re.search(r"^(.*?)(?=上列|主文)", text, re.S)
    if m_header:
        header = m_header.group(1).strip()

    m_main = re.search(r"主文(.*?)(?=理由|$)", text, re.S)
    if m_main:
        main_text = m_main.group(1).strip()

    m_reason = re.search(r"理由(.*?)(?=中華民國|$)", text, re.S)
    if m_reason:
        reason = m_reason.group(1).strip()

    m_footer = re.search(r"(中華民國.*)$", text, re.S)
    if m_footer:
        footer = m_footer.group(1).strip()

    return {
        "header": header,
        "main_text": main_text,
        "reason": reason,
        "footer": footer,
        "clean_text": text
    }

def clean_name(value: str) -> str:
    if not value:
        return ""
    value = value.strip()
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"[（(].*?[）)]", "", value).strip()
    return value

def extract_header_block(text: str) -> str:
    """
    抓判決書前段的標頭區塊，通常包含：
    - 案號
    - 案由
    - 原告 / 被告
    - 聲請人 / 相對人
    - 公訴人
    - 辯護人 / 代理人

    只抓到「上列...」或「主文」之前，避免正文干擾。
    """
    text = preprocess_legal_text(text)

    patterns = [
        r"^(.*?)(?=上列)",
        r"^(.*?)(?=主文)",
    ]

    for p in patterns:
        m = re.search(p, text, re.S)
        if m:
            return m.group(1).strip()

    # 如果抓不到，就退而求其次抓前面一段
    return text[:1500]

def parse_header_entities(text: str) -> dict:
    header = extract_header_block(text)
    lines = [line.strip() for line in header.split("\n") if line.strip()]

    result = {
        "plaintiff": None,
        "defendant": None,
        "applicant": None,
        "respondent": [],
        "prosecutor": None,
        "debtor": None,
        "decedent": None,
        "interested_party": [],
        "lawyers": []
    }

    prefixes = ("原告", "被告", "聲請人", "相對人", "公訴人", "關係人", "被繼承人",
                "法定代理人", "代理人", "選任辯護人", "辯護人", "主文", "理由")

    last_role = None

    for line in lines:
        # 把像「聲 請 人」「相 對 人」這種先正規化
        line = preprocess_legal_text(line)

        if line.startswith("原告"):
            result["plaintiff"] = clean_name(line[len("原告"):])
            last_role = "plaintiff"
            continue

        if line.startswith("被告"):
            result["defendant"] = clean_name(line[len("被告"):])
            last_role = "defendant"
            continue

        if line.startswith("聲請人即債務人"):
            name = clean_name(line[len("聲請人即債務人"):])
            result["applicant"] = name
            result["debtor"] = name
            last_role = "applicant"
            continue

        if line.startswith("聲請人即被告"):
            name = clean_name(line[len("聲請人即被告"):])
            result["applicant"] = name
            result["defendant"] = name
            last_role = "defendant"
            continue

        if line == "聲請人" or line == "相對人" or line == "關係人":
            # 單獨一行的角色標籤，下一行才是名字
            if line == "聲請人":
                last_role = "pending_applicant"
            elif line == "相對人":
                last_role = "pending_respondent"
            elif line == "關係人":
                last_role = "pending_interested_party"
            continue

        if line.startswith("聲請人"):
            name = clean_name(line[len("聲請人"):])
            if name:
                result["applicant"] = name
            last_role = "applicant"
            continue

        if line.startswith("相對人"):
            name = clean_name(line[len("相對人"):])
            if name:
                result["respondent"].append(name)
            last_role = "respondent"
            continue

        if line.startswith("公訴人"):
            result["prosecutor"] = clean_name(line[len("公訴人"):])
            last_role = "prosecutor"
            continue

        if line.startswith("關係人"):
            name = clean_name(line[len("關係人"):])
            if name:
                result["interested_party"].append(name)
            last_role = "interested_party"
            continue

        if line.startswith("被繼承人"):
            result["decedent"] = clean_name(line[len("被繼承人"):])
            last_role = "decedent"
            continue

        # ===== 處理「下一行才是名字」=====
        if last_role == "pending_applicant":
            name = clean_name(line)
            if name and not line.startswith(prefixes):
                result["applicant"] = name
            last_role = "applicant"
            continue

        if last_role == "pending_respondent":
            name = clean_name(line)
            if name and not line.startswith(prefixes):
                result["respondent"].append(name)
            last_role = "respondent"
            continue

        if last_role == "pending_interested_party":
            name = clean_name(line)
            if name and not line.startswith(prefixes):
                result["interested_party"].append(name)
            last_role = "interested_party"
            continue

        # ===== 處理續行，例如相對人多個名字 =====
        if last_role == "respondent":
            name = clean_name(line)
            if name and not line.startswith(prefixes) and is_valid_litigant_name(name):
                result["respondent"].append(name)
                continue
            else:
                last_role = None
                continue

        if last_role == "interested_party":
            name = clean_name(line)
            if name and not line.startswith(prefixes) and is_valid_litigant_name(name):
                result["interested_party"].append(name)
                continue
            else:
                last_role = None
                continue

        last_role = None

    # 去重
    result["respondent"] = list(dict.fromkeys(result["respondent"]))
    result["interested_party"] = list(dict.fromkeys(result["interested_party"]))

    return result

def extract_case_type(text: str):
    if "刑事判決" in text or "刑事裁定" in text:
        return "刑事"
    if "民事判決" in text or "民事裁定" in text:
        return "民事"
    if "家事" in text:
        return "家事"
    return "其他"


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

def is_valid_litigant_name(name: str) -> bool:
    if not name:
        return False

    name = name.strip()

    bad_keywords = [
        "案件", "公訴", "裁定如下", "辯護人", "檢察官",
        "聲請", "本院", "羈押", "停止", "如下", "主文", "理由",
        "法官", "書記官", "法院", "條例", "法第", "庭",
        "現於", "羈押中", "本裁定", "費用由", "程序費用"
    ]

    if len(name) > 40:
        return False

    if name in ["原告", "被告", "聲請人", "相對人", "關係人", "被繼承人"]:
        return False

    for kw in bad_keywords:
        if kw in name:
            return False

    return True
def extract_plaintiff(text: str):
    patterns = [
        # 同一行：原 告 Ａ０１
        r"(?m)^\s*原\s*告\s+([^\n，,。；;：:（）()「」『』【】]+?)\s*$",
        # 下一行：原告 \n Ａ０１
        r"原\s*告\s*\n\s*([^\n，,。；;：:（）()「」『』【】]+?)\s*(?:\n|$)",
    ]

    for p in patterns:
        m = re.search(p, text)
        if m:
            candidate = m.group(1).strip()
            if is_valid_litigant_name(candidate):
                return candidate

    return None


def extract_defendant(text: str):
    patterns = [
        # 同一行：被 告 王小明
        r"(?m)^\s*被\s*告\s+([^\n，,。；;：:（）()「」『』【】]+?)\s*$",
        # 下一行：被告 \n 王小明
        r"被\s*告\s*\n\s*([^\n，,。；;：:（）()「」『』【】]+?)\s*(?:\n|$)",
    ]

    for p in patterns:
        m = re.search(p, text)
        if m:
            candidate = m.group(1).strip()
            if is_valid_litigant_name(candidate):
                return candidate

    return None

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

    m = re.search(r"主\s*文(.*)", text, re.S)
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
    return sorted(list(set(results)))


def extract_articles(text: str):
    laws = [
        "家事事件法",
        "民事訴訟法",
        "非訟事件法",
        "民法",
        "刑法",
        "刑事訴訟法",
        "毒品危害防制條例"
    ]
    found = []

    for law in laws:
        # 單個法條
        pattern = rf"{law}第\d+條(?:之\d+)?(?:第\d+項)?"
        found.extend(re.findall(pattern, text))

        # 多個法條合併寫法，例如：
        # 家事事件法第51條、第97條
        grouped_pattern = rf"{law}第\d+條(?:之\d+)?(?:第\d+項)?(?:、第\d+條(?:之\d+)?(?:第\d+項)?)+"
        grouped_matches = re.findall(grouped_pattern, text)

        for gm in grouped_matches:
            first = re.match(rf"({law})第(\d+條(?:之\d+)?(?:第\d+項)?)", gm)
            if not first:
                continue

            law_name = first.group(1)
            first_article = first.group(2)
            found.append(f"{law_name}第{first_article}")

            rest = gm[len(f"{law_name}第{first_article}"):]
            others = re.findall(r"第(\d+條(?:之\d+)?(?:第\d+項)?)", rest)
            for article in others:
                found.append(f"{law_name}第{article}")

    return sorted(list(set(found)))


def normalize_lawyer_role(role: str):
    mapping = {
        "原告訴訟代理人": "原告訴訟代理人",
        "被告訴訟代理人": "被告訴訟代理人",
        "選任辯護人": "選任辯護人",
        "公設辯護人": "公設辯護人",
        "辯護人": "辯護人",
        "訴訟代理人": "訴訟代理人",
        "代理人": "代理人"
    }
    return mapping.get(role, role)


def extract_lawyers(text: str):
    """
    同一位律師只保留最精確的一個角色
    """
    patterns = [
        (r"原告訴訟代理人\s*([^\s\n]+)", "原告訴訟代理人"),
        (r"被告訴訟代理人\s*([^\s\n]+)", "被告訴訟代理人"),
        (r"選任辯護人\s*([^\s\n]+)", "選任辯護人"),
        (r"公設辯護人\s*([^\s\n]+)", "公設辯護人"),
        (r"辯護人\s*([^\s\n]+)", "辯護人"),
        (r"訴訟代理人\s*([^\s\n]+)", "訴訟代理人"),
        (r"代理人\s*([^\s\n]+)", "代理人"),
    ]

    lawyers = []
    remaining_text = text

    for pattern, role in patterns:
        matches = list(re.finditer(pattern, remaining_text))
        spans = []

        for m in matches:
            lawyer_name = clean_name(m.group(1))
            lawyers.append({
                "name": lawyer_name,
                "role": normalize_lawyer_role(role)
            })
            spans.append((m.start(), m.end()))

        # 移掉已匹配文字，避免短角色重複抓到
        for start, end in reversed(spans):
            remaining_text = remaining_text[:start] + " " + remaining_text[end:]

    # 同名律師只保留第一個（也就是最精確的角色）
    result = []
    seen_name = set()
    for item in lawyers:
        if item["name"] not in seen_name:
            seen_name.add(item["name"])
            result.append(item)

    return result


def extract_decision_type(main_text: str, case_type: str):
    if not main_text:
        return "其他"

    text = main_text.replace(" ", "")

    if case_type in ["民事", "家事"]:
        if "駁回" in text:
            return "駁回"
        if "准許" in text:
            return "准許"
        if "應於" in text and "繳納裁判費" in text:
            return "命補裁判費"
        if "移送" in text:
            return "移送"
        if "不得抗告" in text:
            return "不得抗告"
        if "撤回" in text:
            return "撤回"
        return "其他民事裁定"

    if case_type == "刑事":
        if "無罪" in text:
            return "無罪"
        if "有期徒刑" in text or "拘役" in text or "罰金" in text:
            return "有罪"
        if "羈押" in text:
            return "羈押"
        if "具保" in text or "交保" in text:
            return "交保"
        if "限制住居" in text:
            return "限制住居"
        if "駁回上訴" in text:
            return "駁回上訴"
        if "不受理" in text:
            return "不受理"
        if "免訴" in text:
            return "免訴"
        if "緩刑" in text:
            return "緩刑"
        return "其他刑事裁定"

    return "其他"


def process_case(record):
    raw_text = record.get("case_content", "")
    text = preprocess_legal_text(raw_text)
    entities = parse_header_entities(text)
    case_type = record.get("case_type") or extract_case_type(text)
    main_text = extract_main_text(text)
    reason_text = extract_reason_text(text)

    return {
        "plaintiff": entities.get("plaintiff"),
        "defendant": entities.get("defendant"),
        "applicant": entities.get("applicant"),
        "respondent": entities.get("respondent"),
        "prosecutor": entities.get("prosecutor"),
        "debtor": entities.get("debtor"),
        "decedent": entities.get("decedent"),
        "interested_party": entities.get("interested_party"),
        "case_id": record.get("case_id"),
        "case_type": case_type,
        "court": extract_court(text),
        "case_number": extract_case_number(text),
        "judgment_date": extract_judgment_date(text),
        "cause": extract_case_cause(text),
        "judge": extract_judge(text),
        "clerk": extract_clerk(text),
        "main_text": main_text,
        "reason_text": reason_text,
        "articles": extract_articles(text),
        "money": extract_money(text),
        "decision_type": extract_decision_type(main_text, case_type),
        "lawyers": extract_lawyers(text),
        "raw_text": text
    }


if __name__ == "__main__":
    with open("jud_data.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    processed = [process_case(x) for x in data]

    with open("data/processed_cases_v2.json", "w", encoding="utf-8") as f:
        json.dump(processed, f, ensure_ascii=False, indent=2)

    print("欄位抽取完成，輸出到 data/processed_cases.json")