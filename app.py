import html
import re
from collections import Counter
from decimal import Decimal, InvalidOperation, getcontext

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# Высокая точность на всякий случай (не влияет на сравнение — оно точное)
getcontext().prec = 60

DEFAULT_NUM_RE = r"[-+]?(?:\d+\.\d+|\.\d+|\d+)(?:[eE][-+]?\d+)?"

st.set_page_config(page_title="Сравнение чисел — Бухгалтерия", page_icon="🧮", layout="wide")

st.title("🧮 Сравнение чисел — без погрешностей")
st.caption(
    "Все числа сравниваются как `Decimal` — точно, без округления, "
    "без допусков, без сюрпризов `float`. Для бухгалтерии."
)

# ═══════════════════════════════════════════════════
#                  НАСТРОЙКИ
# ═══════════════════════════════════════════════════
with st.sidebar:
    st.header("⚙️ Настройки")

    st.subheader("Формат чисел в файлах")
    format_choice = st.selectbox(
        "Как записаны числа",
        [
            "1 234,56 — пробел тыс., запятая дес.",
            "1,234.56 — запятая тыс., точка дес.",
            "1.234,56 — точка тыс., запятая дес.",
            "1234.56 — без разделителей, точка",
            "1234,56 — без разделителей, запятая",
            "Автоопределение (эвристика, не рекомендуется)",
        ],
        help="Для точности выбирайте явно. 'Авто' может ошибиться на '1,234'.",
    )

    parens_neg = st.checkbox(
        "(123,45) = -123,45",
        value=False,
        help="Бухгалтерская запись отрицательных чисел в скобках",
    )

    st.subheader("Сравнение")
    mode = st.radio("Режим", ["По позициям", "Как множество (без порядка)"])

    st.subheader("Отображение")
    show_highlighted = st.checkbox("Подсветка в исходном тексте", value=True)
    show_decimals = st.checkbox("Показывать нормализованные Decimal-значения", value=True)

# ═══════════════════════════════════════════════════
#              ПАРСИНГ ЧИСЕЛ В DECIMAL
# ═══════════════════════════════════════════════════
def _clean_spaces(s: str) -> str:
    for ch in ("\u00a0", "\u202f", "\u2009", "\u2007", " "):
        s = s.replace(ch, "")
    return s


def _parse_auto(s: str) -> Decimal:
    has_c, has_d = "," in s, "." in s
    if has_c and has_d:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif has_c:
        s = s.replace(",", "") if s.count(",") > 1 else s.replace(",", ".")
    elif has_d and s.count(".") > 1:
        s = s.replace(".", "")
    return Decimal(s)


def parse_decimal(raw: str, fmt: str, parens_neg: bool) -> Decimal | None:
    s = raw.strip()
    neg = False
    if parens_neg and s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    s = _clean_spaces(s)

    try:
        if fmt.startswith("1 234,56"):
            d = Decimal(s.replace(",", "."))
        elif fmt.startswith("1,234.56"):
            d = Decimal(s.replace(",", ""))
        elif fmt.startswith("1.234,56"):
            d = Decimal(s.replace(".", "").replace(",", "."))
        elif fmt.startswith("1234.56"):
            d = Decimal(s)
        elif fmt.startswith("1234,56"):
            d = Decimal(s.replace(",", "."))
        else:
            d = _parse_auto(s)
    except InvalidOperation:
        return None

    return -d if neg else d


# ═══════════════════════════════════════════════════
#                ЧТЕНИЕ ФАЙЛОВ
# ═══════════════════════════════════════════════════
def read_file(f) -> str | None:
    name = f.name.lower()
    try:
        if name.endswith((".xlsx", ".xls")):
            df = pd.read_excel(f, header=None, dtype=str)
            return "\n".join(str(v) for v in df.values.flatten() if pd.notna(v))
        raw = f.read()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("cp1251", errors="replace")
    except Exception as e:
        st.error(f"Не удалось прочитать {f.name}: {e}")
        return None


# ═══════════════════════════════════════════════════
#                 ЗАГРУЗКА ФАЙЛОВ
# ═══════════════════════════════════════════════════
files = st.file_uploader(
    "Загрузите файлы (минимум 2)",
    accept_multiple_files=True,
    type=["txt", "csv", "log", "xlsx", "xls", "tsv", "dat"],
)

if not files or len(files) < 2:
    st.info("👆 Загрузите минимум два файла для сравнения")
    st.stop()

regex = re.compile(DEFAULT_NUM_RE)
file_data = []

for f in files:
    text = read_file(f)
    if text is None:
        continue
    nums = []
    for m in regex.finditer(text):
        raw = m.group(0)
        nums.append({
            "raw": raw,
            "dec": parse_decimal(raw, format_choice, parens_neg),
            "start": m.start(),
            "end": m.end(),
        })
    file_data.append({"name": f.name, "text": text, "nums": nums})

if len(file_data) < 2:
    st.stop()

# ── Предупреждения о неразборчивых числах ──
for fd in file_data:
    bad = [n["raw"] for n in fd["nums"] if n["dec"] is None]
    if bad:
        st.warning(
            f"⚠️ **{fd['name']}**: не удалось распознать {len(bad)} чисел "
            f"(проверьте формат). Примеры: `{bad[:5]}`"
        )

# ── Статистика ──
st.subheader("📊 Статистика")
cols = st.columns(len(file_data))
for col, fd in zip(cols, file_data):
    col.metric(fd["name"], f"{len(fd['nums'])} чисел")

counts = [len(fd["nums"]) for fd in file_data]
if len(set(counts)) > 1:
    st.warning("⚠️ В файлах разное количество чисел — «хвосты» будут отмечены как различия.")

# ═══════════════════════════════════════════════════
#                 СРАВНЕНИЕ
# ═══════════════════════════════════════════════════
if mode == "По позициям":
    max_count = max(len(fd["nums"]) for fd in file_data)
    rows = []

    for i in range(max_count):
        cells = [
            fd["nums"][i] if i < len(fd["nums"]) else None
            for fd in file_data
        ]
        decs = [c["dec"] if c is not None else None for c in cells]

        is_diff = False
        if any(c is None for c in cells):          # у кого-то нет числа
            is_diff = True
        elif any(d is None for d in decs):          # что-то не распарсилось
            is_diff = True
        elif len(set(decs)) > 1:                    # точное сравнение Decimal
            is_diff = True

        rows.append({"cells": cells, "decs": decs, "is_diff": is_diff})

    st.subheader("🔍 Результат сравнения")

    # ── Таблица ──
    header = ["#"] + [fd["name"] for fd in file_data]
    data_raw = [
        [i + 1] + [c["raw"] if c else "—" for c in r["cells"]]
        for i, r in enumerate(rows)
    ]
    df_raw = pd.DataFrame(data_raw, columns=header)

    def style_row(row):
        return (
            ["background-color:#ffd6d6;font-weight:bold;color:#b00020"] * len(row)
            if rows[row.name]["is_diff"]
            else [""] * len(row)
        )

    st.dataframe(df_raw.style.apply(style_row, axis=1),
                 use_container_width=True, height=480)

    # ── Нормализованные Decimal-значения ──
    if show_decimals:
        with st.expander("🔎 Нормализованные Decimal-значения (как сравниваются)"):
            data_dec = [
                [i + 1] + [
                    str(c["dec"]) if c and c["dec"] is not None else "⚠️"
                    for c in r["cells"]
                ]
                for i, r in enumerate(rows)
            ]
            df_dec = pd.DataFrame(data_dec, columns=header)
            st.dataframe(df_dec.style.apply(style_row, axis=1),
                         use_container_width=True, height=400)
            st.caption(
                "Сравнение выполняется по этим значениям через `Decimal`. "
                "`100.00` и `100` — равны, `0.1 + 0.2` и `0.3` — равны, "
                "`12345678901234567890` и `...891` — различны."
            )

    # ── Итог ──
    n_diff = sum(1 for r in rows if r["is_diff"])
    if n_diff == 0:
        st.success(f"✅ Все числа точно совпадают ({len(rows)} позиций)")
    else:
        st.error(f"❌ Найдено {n_diff} различающихся позиций из {len(rows)}")

    # ── Экспорт ──
    export = []
    for i, r in enumerate(rows):
        row = {"#": i + 1, "status": "DIFF" if r["is_diff"] else "OK"}
        for j, c in enumerate(r["cells"]):
            name = file_data[j]["name"]
            row[f"{name} (raw)"] = c["raw"] if c else ""
            row[f"{name} (decimal)"] = (
                str(c["dec"]) if c and c["dec"] is not None else ""
            )
        export.append(row)
    st.download_button(
        "💾 Скачать результат (CSV, UTF-8-BOM — открывается в Excel)",
        pd.DataFrame(export).to_csv(index=False).encode("utf-8-sig"),
        file_name="diff.csv",
        mime="text/csv",
    )

    # ── Подсветка в исходном тексте ──
    if show_highlighted:
        st.subheader("📄 Текст с подсветкой различий")
        for fd in file_data:
            st.markdown(f"**{fd['name']}**")
            parts, last = [], 0
            for i, n in enumerate(fd["nums"]):
                parts.append(html.escape(fd["text"][last:n["start"]]))
                is_diff = i < len(rows) and rows[i]["is_diff"]
                style = (
                    "background:#ffd6d6;color:#b00020;font-weight:bold;"
                    "padding:1px 4px;border-radius:3px"
                    if is_diff else ""
                )
                parts.append(f'<span style="{style}">{html.escape(n["raw"])}</span>')
                last = n["end"]
            parts.append(html.escape(fd["text"][last:]))
            components.html(
                '<div style="font-family:monospace;font-size:13px;'
                'padding:12px;background:#fafafa;border:1px solid #ddd;'
                'border-radius:6px;height:340px;overflow-y:auto;'
                f'white-space:pre-wrap;word-break:break-word">{"".join(parts)}</div>',
                height=360,
            )

else:
    # ═══════════════════════════════════════════
    #            РЕЖИМ «МНОЖЕСТВО»
    # ═══════════════════════════════════════════
    st.subheader("🔍 Результат сравнения (как множество)")

    counters = []
    for fd in file_data:
        c = Counter(n["dec"] for n in fd["nums"] if n["dec"] is not None)
        counters.append(c)

    all_keys = sorted(set().union(*[set(c) for c in counters]))

    header = ["Число (Decimal)"] + [fd["name"] for fd in file_data]
    data = [[str(k)] + [c.get(k, 0) for c in counters] for k in all_keys]
    df = pd.DataFrame(data, columns=header)

    def style_set(row):
        return (
            ["background-color:#ffd6d6;font-weight:bold;color:#b00020"] * len(row)
            if len(set(row[1:].tolist())) > 1 else [""] * len(row)
        )

    st.dataframe(df.style.apply(style_set, axis=1),
                 use_container_width=True, height=480)

    n_diff = sum(1 for row in data if len(set(row[1:])) > 1)
    if n_diff == 0:
        st.success("✅ Наборы чисел полностью совпадают")
    else:
        st.error(f"❌ {n_diff} чисел имеют разное количество вхождений")

    st.download_button(
        "💾 Скачать результат (CSV)",
        df.to_csv(index=False).encode("utf-8-sig"),
        file_name="diff_set.csv",
        mime="text/csv",
    )