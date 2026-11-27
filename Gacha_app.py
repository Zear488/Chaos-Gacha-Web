import streamlit as st
import pandas as pd
import io
import random
import os
import re
from streamlit.components.v1 import html
from logic import perform_gacha_draw, GachaHistoryTracker
from logic.tracker import GachaHistoryTracker
from logic.gacha_engine import perform_gacha_draw
from logic.roll_manager import (
    sync_roll_instances, get_inventory, clear_inventory, InventoryDataError,
    equip_roll, unequip_roll, get_equipment_slots, InventoryStateError,
    EQUIPMENT_CATEGORIES, discard_roll,
)
from logic.history_csv import parse_history_csv, strip_import_metadata, serialize_history_csv
from character.parser import parse_stats, parse_resistances
from character.progression import (
    STAT_NAMES, get_level_from_pulls, get_progress_to_next_level,
    points_earned_for_level, load_character_progress, allocate_stat_points,
    clear_character_progress,
)
import numpy as np
import math
import altair as alt
import time
from datetime import datetime

tracker = GachaHistoryTracker()

# ------------------ CONFIG ------------------
st.set_page_config(page_title="Chaos Gacha Web", layout="wide")
if tracker.points_error:
    st.sidebar.error(
        f"Transcendent Points file could not be read safely: {tracker.points_error} "
        "The original file has been preserved; point-changing actions are disabled."
    )

# ------------------ LOAD EXISTING HISTORY ------------------
st.sidebar.header("📂 Load Previous History")

uploaded_file = st.sidebar.file_uploader("Upload history CSV (UTF-8)", type=["csv"])
manual_csv = st.sidebar.text_area("📋 Or paste CSV content manually", key="manual_csv")

if "log" not in st.session_state:
    st.session_state["log"] = []

def load_csv_data(content: str):
    global tracker
    try:
        imported_rows = parse_history_csv(content)
        if not imported_rows:
            st.sidebar.warning("The CSV contains no pull records.")
            return False

        st.session_state["log"] = [
            strip_import_metadata(row) for row in imported_rows
        ]
        sync_roll_instances(imported_rows)
        tracker.load_from_log(st.session_state["log"])

        st.sidebar.success(
            f"History loaded successfully: {len(imported_rows)} pull(s) restored."
        )
        return True
    except Exception as error:
        st.sidebar.error(f"Invalid history CSV: {error}")
        return False

# Loading is explicit and performed once per click. Never assign to the
# text_area's own session_state key after its widget has been instantiated.
if uploaded_file is not None:
    uploaded_content = uploaded_file.getvalue().decode("utf-8-sig")
    if st.sidebar.button("Load uploaded CSV", key="load_uploaded_history"):
        load_csv_data(uploaded_content)

if manual_csv.strip():
    if st.sidebar.button("Load pasted CSV", key="load_pasted_history"):
        load_csv_data(manual_csv.strip())

# Ayuda visual
with st.sidebar.expander("📘 CSV Format Help"):
    st.markdown("""
    Paste content **with tabs between fields**, like this:

    ```
    Type	Element	Rarity	Tier	Luck	Description	Color
    Ability	862.Bountiful Harvest	1.7	Common	50.00%	You are able to create ripe and tasty fruits and vegetables by expending your own energy.	#9c7e5a
    Ability	751. Fake Weapon	0.7	Trash	81.25%	Allows you to create illusionary weapons in your hands for intimidation purposes.	#a39589
    ```
    """)
# Borrar historial y archivos JSON asociados
if st.sidebar.button("🗑️ Clear History"):
    st.session_state["log"] = []
    st.session_state["csv_data"] = None
    st.session_state["show_history"] = False
    st.session_state["rendering_log"] = False
    tracker.clear_all()
    clear_inventory()
    clear_character_progress()

    # Remove the persisted raw gacha history as well as the JSON state.
    history_path = os.path.join("logs", "gacha_history.csv")
    if os.path.exists(history_path):
        os.remove(history_path)

    st.sidebar.success("Gacha history, inventory, and TP data cleared.")

# Mostrar puntos actuales
st.sidebar.markdown(f"⭐ Transcendent Points: `{tracker.get_points():.3f}`")

# ------------------ READ FUNCTION ------------------

def read_file_with_weight(filename, avg, min_val, max_val):
    elements, weights, rarities, descriptions = [], [], [], []

    min_rarity = float(min_val)
    avg_rarity = float(avg)
    max_rarity = float(max_val)
    sigma = 1.2
    skew_strength = 0.6  # Controla cuánto se aplana del lado derecho

    def custom_weight(rarity):
        x = (rarity - avg_rarity) / sigma
        skew = 1.0 + skew_strength if rarity > avg_rarity else 1.0 - skew_strength
        return math.exp(-x * x * skew)

    if filename == "Random":
        filename = random.choice(["Ability", "Item", "Familiar", "Trait", "Skill"])

    chosentype = filename.capitalize()
    path = os.path.join("gachafiles", f"{filename}.txt")

    with open(path, "r", encoding="utf-8") as file:
        temp_description = []

        for line in file:
            match = re.match(r"^(\d+)\.(\S*)\s*(.*)", line)
            if match:
                parts = line.strip().split(",")
                if len(parts) >= 2:
                    element = parts[0].strip()
                    try:
                        rarity = float(parts[1])
                    except ValueError:
                        continue

                    elements.append(element)
                    rarities.append(rarity)
                    weight = custom_weight(rarity)
                    weights.append(weight)

                    if temp_description:
                        descriptions.append("".join(temp_description).strip())
                        temp_description = []
            else:
                temp_description.append(line)

        if temp_description:
            descriptions.append("".join(temp_description).strip())

    weightsum = sum(weights)

    return elements, weights, rarities, descriptions, weightsum, chosentype
# ------------------ GACHA FUNCTIONS ------------------

def randomizer(min_val, max_val, avg, std_dev=0.8, bonus_chance=0.0048, bonus_max=2.0, max_penalty=0.7, max_attempts=10):
    min_val = float(min_val)
    max_val = float(max_val)
    avg = float(avg)

    for attempt in range(1, max_attempts + 1):
        # Penalización progresiva al promedio para permitir encontrar algo cercano
        penalty_factor = 1 - min(max_penalty, (attempt - 1) * 0.07)  # Límite: -70%
        capped_avg = avg * penalty_factor
        rarity = random.gauss(capped_avg, std_dev)

        # Bonus de rareza ocasional
        if random.random() < bonus_chance:
            rarity += random.uniform(0.1, bonus_max)

        # Clampeamos dentro de los límites
        rarity = max(min_val, min(rarity, max_val))

        if min_val <= rarity <= max_val:
            return round(rarity, 2)
    # Si falla todo, retorna el peor resultado
    return round(min_val, 2)
    
def perform_gacha_draw(mode, min_val, avg, max_val, num_pulls=1, boost_transcendent=False, max_tries=10):
    results = []
    elements, base_weights, rarities, descriptions, _, chosentype = read_file_with_weight(mode, avg, min_val, max_val)

    for _ in range(num_pulls):
        for attempt in range(1, max_tries + 1):
            raritypull = randomizer(min_val, max_val, avg, std_dev=0.8)

            filtered = [(e, w, r, d) for e, w, r, d in zip(elements, base_weights, rarities, descriptions)
                        if abs(r - raritypull) <= 0.25]

            if filtered:
                adjusted_weights = [w for _, w, _, _ in filtered]
                filtered_weights_sum = sum(adjusted_weights)
                if filtered_weights_sum == 0:
                    break

                selected = random.choices(filtered, weights=adjusted_weights)[0]
                element, _, rarity, desc = selected
                bonus_triggered = False

                base_star_chance = 0.0048
                tp = tracker.get_points()
                boost_star_chance = 0.0

                if boost_transcendent and tp >= 5:
                    boost_star_chance = min(0.0023 * tp, 0.50)

                total_star_chance = base_star_chance + boost_star_chance

                # Nuevo bonus estrella con reevaluación y microajuste aleatorio
                if random.random() < total_star_chance and rarity + 2 <= 10:
                    enhanced_rarity = min(10.0, rarity + 2)

                    upgraded = [(e, w, r, d) for e, w, r, d in zip(elements, base_weights, rarities, descriptions)
                                if abs(r - enhanced_rarity) <= 0.25]

                    if upgraded:
                        selected = random.choices(upgraded, weights=[w for _, w, _, _ in upgraded])[0]
                        element, _, rarity, desc = selected
                        rarity = round(rarity + random.uniform(0.05, 0.40), 2)  # microajuste aleatorio

                    element = f"★ {element}"
                    bonus_triggered = True

                rarity_range = max_val - min_val
                if rarity_range == 0:
                    estimated_luck = 100.0
                else:
                    distance_from_min = rarity - min_val
                    estimated_luck = max(0.1, min(100.0, 100.0 * (1 - (distance_from_min / rarity_range))))

                tier, color = get_tier_and_color(rarity)
                pull_data = {
                    "Type": chosentype,
                    "Element": element,
                    "Rarity": f"{round(rarity, 2):.2f}",
                    "Tier": tier,
                    "LuckValue": round(estimated_luck, 2),  # Valor numérico puro
                    "Luck": f"{round(estimated_luck, 2):.2f}%",  # Valor con formato
                    "Description": desc.strip(),
                    "Color": color,
                    "Notes": ""
                }
                notes = []
                if tracker.check_repeat(pull_data):
                    notes.append("🔁 Repeated — +1 TP")

                if bonus_triggered and boost_star_chance > 0:
                    if tracker.spend_points(tp):
                        notes.append(f"✨ Boosted Star Bonus — -{tp} TP")

                if notes:
                    pull_data["Notes"] = " | ".join(notes)

                results.append(pull_data)
                break

    return results

def get_tier_and_color(rarity):
    tiers = [
        (1.0, 'Trash', '#a39589'),
        (2.0, 'Common', '#9c7e5a'),
        (3.0, 'Uncommon', '#aed1d1'),
        (4.0, 'Rare', '#11d939'),
        (5.0, 'Elite', '#1172d9'),
        (6.0, 'Epic', '#6811d9'),
        (7.0, 'Legendary', '#f7d40a'),
        (8.0, 'Mythical', '#fc61ff'),
        (9.0, 'Divine', '#ff8c00'),
        (10.0, 'Transcendent', '#ff0000'),
    ]
    for limit, name, color in tiers:
        if rarity < limit:
            return name, color
    return "Transcendent", "#ff0000"

# ------------------ STREAMLIT INTERFACE ------------------
st.title("🎲 Chaos Gacha Web")

with st.expander("ℹ️ What do 'Rarity' and 'Estimated Luck' mean?"):
    st.markdown("""
    **🧪 Rarity** is a value between `0.1` and `10.0` that represents 
    how special or powerful an element is. The higher the number, the rarer it is.

    | Tier           | Rarity Range   | Color        |
    |----------------|----------------|--------------|
    | Trash          | < 1.0          | Brown        |
    | Common         | 1.0 – 2.0      | Bronze       |
    | Uncommon       | 2.0 – 3.0      | Teal         |
    | Rare           | 3.0 – 4.0      | Green        |
    | Elite          | 4.0 – 5.0      | Blue         |
    | Epic           | 5.0 – 6.0      | Purple       |
    | Legendary      | 6.0 – 7.0      | Gold         |
    | Mythical       | 7.0 – 8.0      | Pink         |
    | Divine         | 8.0 – 9.0      | Orange       |
    | Transcendent   | > 9.0          | Red          |

    ---

    **🍀 Estimated Luck** shows how unlikely it was to pull this element:

    | Estimated Luck | Interpretation             |
    |----------------|----------------------------|
    | > 30%          | Very Common                |
    | 10% – 30%      | Uncommon                   |
    | 1% – 10%       | Rare                       |
    | < 1%           | Extremely Rare / Epic Pull |

    The lower the percentage, the luckier you were. 
    This value is calculated based on the rarity and the configured search range.
    """)

presets = {
    "Bronze": ((0.1, 1.3, 3.3), "#cd7f32"),
    "Silver": ((0.5, 2.3, 4.3), "#c0c0c0"),
    "Gold": ((1.5, 3.3, 5.3), "#ffd700"),
    "Platinum": ((2.5, 4.3, 6.3), "#e5e4e2"),
    "Diamond": ((3.5, 5.3, 7.3), "#b9f2ff"),
    "Legendary": ((4.5, 6.3, 8.3), "#f7d40a"),
    "Mythical": ((5.5, 7.3, 9.3), "#fc61ff"),
    "Divine": ((6.5, 8.3, 10.0), "#ff8c00"),
}

if "min_val" not in st.session_state:
    st.session_state["min_val"] = 0.1
    st.session_state["avg"] = 1.3
    st.session_state["max_val"] = 3.3

if "log" not in st.session_state:
    st.session_state["log"] = []

st.subheader("🎚️ Choose a Rarity Preset")
cols = st.columns(len(presets))

for i, (label, (values, color)) in enumerate(presets.items()):
    with cols[i]:
        clicked = st.button(label, use_container_width=True, key=f"preset_{label}")
        if clicked:
            st.session_state["min_val"], st.session_state["avg"], st.session_state["max_val"] = values
        st.markdown(
            f"<div style='height:6px;background-color:{color};border-radius:4px;margin-top:4px;'></div>",
            unsafe_allow_html=True
        )

active_color = "#4a4a4a"
for label, (values, color) in presets.items():
    if (st.session_state["min_val"], st.session_state["avg"], st.session_state["max_val"]) == values:
        active_color = color
        break

st.subheader("Category")
mode = st.radio("Choose a category", ["Ability", "Item", "Familiar", "Skill", "Trait", "Random"], horizontal=True)

st.subheader("Rarity Range")
min_val = st.slider("Min", 0.0, 10.0, st.session_state["min_val"], 0.1)
avg = st.slider("Average", 0.0, 10.0, st.session_state["avg"], 0.1)
max_val = st.slider("Max", 0.0, 10.0, st.session_state["max_val"], 0.1)

st.session_state["min_val"] = min_val
st.session_state["avg"] = avg
st.session_state["max_val"] = max_val

# Selector + Botón de Multi Pull
# Selector de multipull
pull_count = st.selectbox("Select number of pulls:", [1, 2, 5, 10], index=0)

def classify_luck(luck_value):
    if luck_value > 95:
        return "Below Average"
    elif luck_value > 75:
        return "Average"
    elif luck_value > 55:
        return "Above Average"
    elif luck_value > 35:
        return "Notable"
    elif luck_value > 15:
        return "Rare"
    elif luck_value > 5:
        return "Exceptional Pull"
    else:
        return "Mythic Pull"

# Función para mostrar un resultado
def display_result(result, min_val, max_val):
    tier, color = get_tier_and_color(float(result["Rarity"]))
    if "LuckValue" in result:
        luck_value = float(result["LuckValue"])
    else:
        luck_value = float(result["Luck"].replace('%', ''))
    luck_type = classify_luck(luck_value)

    notes = result.get("Notes", "")
    is_boosted_star = "Boosted Star Bonus" in notes

    star_icon = "🎉🎉" if is_boosted_star else ""
    boost_msg = f"<span style='color:#ffcc00;font-weight:bold;'>✨ Boosted Star Bonus Activated!</span><br>" if is_boosted_star else ""
    border_style = "3px solid #ffcc00" if is_boosted_star else "1px solid #444"

    st.markdown(f"<h3 style='color:{color}' title='{result['Description']}'>{star_icon} 🎉 {result['Element']}</h3>", unsafe_allow_html=True)
    st.markdown(f"<span style='color:{color}'><strong>Rarity</strong>: `{float(result['Rarity']):.2f}` ({tier})</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='color:{color}'><strong>Type</strong>: `{result['Type']}`</span>", unsafe_allow_html=True)
    st.markdown(f"<span style='color:{color}'><strong>Estimated Luck</strong>: `{result['Luck']}` – {luck_type}</span>", unsafe_allow_html=True)

    if notes:
        st.markdown(f"<span style='color:#cccccc;'><strong>Notes:</strong> {notes}</span>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(
        f"<div style='background-color:#111;padding:10px;border-radius:10px;border:{border_style};'>"
        f"{boost_msg}"
        f"<p style='color:white;font-size:16px;line-height:1.5;text-align:justify;'>{result['Description']}</p>"
        f"</div>",
        unsafe_allow_html=True
    )

    log_entry = {
        "Type": result["Type"],
        "Element": result["Element"],
        "Rarity": result["Rarity"],
        "Tier": result["Tier"],
        "Luck": result["Luck"],
        "Description": result["Description"],
        "Color": result["Color"],
        "Notes": notes
    }

# Botón individual 🎰 Roll
# Al hacer una tirada, desactiva la variable csv_data para evitar pre-render CSV

# Inicializar control anti-spam si no existe
if "last_click_time" not in st.session_state:
    st.session_state["last_click_time"] = 0

# Tiempo mínimo entre clics (en segundos)
CLICK_DELAY = 0.2

# 🎰 Roll 
if st.button("🎰 Roll", type="primary"):
    now = time.time()
    if now - st.session_state["last_click_time"] >= CLICK_DELAY:
        st.session_state["last_click_time"] = now
        st.session_state["csv_data"] = None  # 🚫 Evitar generación automática
        results = perform_gacha_draw(mode, min_val, avg, max_val, num_pulls=1, boost_transcendent=True)
        new_entries = []
        result_container = st.container()
        with result_container:
            for result in results:
                if result:
                    display_result(result, min_val, max_val)
                    new_entries.append(result)
        st.session_state["log"].extend(new_entries)
        tracker.load_from_log(st.session_state["log"])
        sync_roll_instances(st.session_state["log"])
        df_auto = pd.DataFrame(st.session_state["log"])
        df_auto.to_csv("logs/gacha_history.csv", index=False, encoding="utf-8-sig")
        st.session_state["show_curve_analysis"] = False
    else:
        st.warning("⏳ Please wait a moment before clicking again.")

# 🎲 Multi-Roll 
if st.button("🎲 Multi-Roll"):
    now = time.time()
    if now - st.session_state["last_click_time"] >= CLICK_DELAY:
        st.session_state["last_click_time"] = now
        st.session_state["csv_data"] = None  # 🚫 Evitar generación automática
        results = perform_gacha_draw(mode, min_val, avg, max_val, num_pulls=pull_count, boost_transcendent=True)
        new_entries = []
        result_container = st.container()
        with result_container:
            for result in results:
                if result:
                    display_result(result, min_val, max_val)
                    new_entries.append(result)
        st.session_state["log"].extend(new_entries)
        tracker.load_from_log(st.session_state["log"])
        sync_roll_instances(st.session_state["log"])
        df_auto = pd.DataFrame(st.session_state["log"])
        df_auto.to_csv("logs/gacha_history.csv", index=False, encoding="utf-8-sig")
        st.session_state["show_curve_analysis"] = False
    else:
        st.warning("⏳ Please wait a moment before clicking again.")


# Mostrar historial y permitir descarga solo después de al menos una tirada
if st.session_state.get("log"):
    if "show_history" not in st.session_state:
        st.session_state["show_history"] = False

    if st.button("📜 Show Roll History"):
        st.session_state["show_history"] = not st.session_state["show_history"]

    if st.session_state["show_history"] and not st.session_state.get("rendering_log"):
        st.session_state["rendering_log"] = True

        st.markdown("## 📜 Roll History")
        st.markdown(f"Total Rolls: **{len(st.session_state['log'])}**")

        log_html = """
        <div style='
            max-height: 500px;
            overflow-y: auto;
            padding-right: 10px;
            margin-bottom: 20px;
            border: 1px solid #333;
            border-radius: 10px;
            padding: 10px;
            background-color: #1e1e1e;
        '>
        """
        for i, entry in enumerate(reversed(st.session_state["log"]), 1):
            color = entry.get("Color", "#f0f0f0")
            log_html += f"""
            <div style='
                background-color:#222;
                padding:15px;
                margin:10px 0;
                border-radius:10px;
                box-shadow:0 0 5px rgba(255,255,255,0.1);
            '>
                <h4 style='color:{color};margin-bottom:5px;'>#{len(st.session_state["log"]) - i + 1} — {entry.get("Element", "Unknown")}</h4>
                <p style='margin:2px 0;color:{color};'><strong>Type:</strong> {entry.get("Type", "-")}</p>
                <p style='margin:2px 0;color:{color};'><strong>Rarity:</strong> {entry.get("Rarity", "-")} ({entry.get("Tier", "-")})</p>
                <p style='margin:2px 0;color:{color};'><strong>Luck:</strong> {entry.get("Luck", "-")}</p>
                <p style='margin:10px 0 0 0;'><strong>Description:</strong></p>
                <div style='
                    background-color:#111;
                    padding:10px;
                    border-radius:8px;
                    color:#ddd;
                    font-size:14px;
                    white-space:pre-wrap;
                    word-wrap:break-word;
                '>{entry.get("Description", "No description")}</div>
            </div>
            """
        log_html += "</div>"

        html(log_html, height=550)

        st.session_state["rendering_log"] = False

        df_log = pd.DataFrame([
            strip_import_metadata(row) for row in st.session_state["log"]
        ])
        columns_order = ["Type", "Element", "Rarity", "Tier", "LuckValue", "Luck", "Description", "Color", "Notes"]
        df_log = df_log[[col for col in columns_order if col in df_log.columns]]

        if st.button("⬇️ Generate Complete CSV File"):
            st.session_state["csv_data"] = serialize_history_csv(
                st.session_state["log"],
                get_inventory(),
            )

        if st.session_state.get("csv_data"):
            st.download_button(
                label="📥 Download Complete History as CSV",
                data=st.session_state["csv_data"],
                file_name="gacha_history.csv",
                mime="text/csv"
            )


# Carpetas que usadas:
# - "Original_gachafiles" para los archivos originales
# - "gachafiles" para los archivos editados actuales
# - "gachafiles_versions" para versiones guardadas (historial)

# Crear carpetas si no existen
for folder in ["Original_gachafiles", "gachafiles", "gachafiles_versions"]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# Inicializar session_state
if "original_files" not in st.session_state:
    st.session_state["original_files"] = {}

if "edited_files" not in st.session_state:
    st.session_state["edited_files"] = {}

# Lista de gachafiles según carpeta "gachafiles"
gachafile_options = [f.replace(".txt", "") for f in os.listdir("gachafiles") if f.endswith(".txt")]
selected_gachafile = st.selectbox("Select a Gacha File to view/edit", gachafile_options)

# Cargar original si no existe en session_state (desde Original_gachafiles)
if selected_gachafile not in st.session_state["original_files"]:
    path_original = os.path.join("Original_gachafiles", f"{selected_gachafile}.txt")
    with open(path_original, "r", encoding="utf-8") as f:
        content = f.read()
    st.session_state["original_files"][selected_gachafile] = content

# Cargar editado si no existe (desde gachafiles)
if selected_gachafile not in st.session_state["edited_files"]:
    path_edit = os.path.join("gachafiles", f"{selected_gachafile}.txt")
    with open(path_edit, "r", encoding="utf-8") as f:
        content_edit = f.read()
    st.session_state["edited_files"][selected_gachafile] = content_edit

edit_key = f"edit_area_{selected_gachafile}"

# Inicializar textarea controlado
if edit_key not in st.session_state:
    st.session_state[edit_key] = st.session_state["edited_files"][selected_gachafile]

# Botón Restore Original
if st.button("♻️ Restore Original"):
    st.session_state[edit_key] = st.session_state["original_files"][selected_gachafile]
    st.session_state["edited_files"][selected_gachafile] = st.session_state["original_files"][selected_gachafile]
    st.success(f"Restored original `{selected_gachafile}`.")

# Mostrar textarea editable
content = st.text_area(
    label=f"Edit {selected_gachafile}",
    value=st.session_state[edit_key],
    key=edit_key,
    height=300,
)

# Actualizar el contenido editado en session_state
st.session_state["edited_files"][selected_gachafile] = st.session_state[edit_key]

# Botón Guardar cambios manual
if st.button("💾 Save Changes"):
    path = os.path.join("gachafiles", f"{selected_gachafile}.txt")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(st.session_state["edited_files"][selected_gachafile])
        st.success(f"✅ Changes saved to `{selected_gachafile}.txt`.")

        # Guardar versión automática con timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        version_path = os.path.join("gachafiles_versions", f"{selected_gachafile}_{timestamp}.txt")
        with open(version_path, "w", encoding="utf-8") as f:
            f.write(st.session_state["edited_files"][selected_gachafile])

    except Exception as e:
        st.error(f"❌ Error saving file: {e}")

st.markdown("---")
st.subheader("Saved Versions")

import base64

st.markdown("## 📜 Saved Versions")

version_folder = "gachafiles_versions"
file_prefix = selected_gachafile + "_"

# Buscar versiones guardadas del archivo actual
version_files = sorted(
    [f for f in os.listdir(version_folder) if f.startswith(file_prefix)],
    reverse=True
    
)

if "editable_gachafiles" not in st.session_state:
    st.session_state.editable_gachafiles = {}
    
if version_files:
    for version_file in version_files:
        version_path = os.path.join(version_folder, version_file)
        col1, col2, col3, col4 = st.columns([4, 1, 1, 1])
        
        with col1:
            st.markdown(f"📂 `{version_file}`")

        with col2:
            if st.button("🔄 Restore", key=f"restore_{version_file}"):
                with open(version_path, "r", encoding="utf-8") as f:
                    st.session_state.editable_gachafiles[selected_gachafile] = f.read()
                st.success(f"✅ Restored version: {version_file}")

        with col3:
            if st.button("🗑️ Delete", key=f"delete_{version_file}"):
                try:
                    os.remove(version_path)
                    st.success(f"🗑️ Deleted version: {version_file}")
                except Exception as e:
                    st.error(f"❌ Error deleting version: {e}")

        with col4:
            with open(version_path, "rb") as f:
                file_content = f.read()
                b64 = base64.b64encode(file_content).decode()
                href = f'<a href="data:file/txt;base64,{b64}" download="{version_file}">⬇️ Download</a>'
                st.markdown(href, unsafe_allow_html=True)
else:
    st.info("No saved versions available for this file.")

    st.markdown("## 🗑️ Manage Saved Versions")

version_folder = "gachafiles_versions"

if not os.path.exists(version_folder):
    os.makedirs(version_folder)

# -------------------------------
# Borrar versiones del archivo actual
# -------------------------------
file_prefix = selected_gachafile + "_"
version_files = [
    f for f in os.listdir(version_folder)
    if f.startswith(file_prefix) and f.endswith(".txt")
]

st.markdown("### 🔍 Delete Versions for Current File")

if version_files:
    selected_versions = st.multiselect(
        "Select versions to delete:",
        version_files,
        help="These are saved historical versions of the current file."
       
    )
    if st.button("❌ Delete Selected Versions"):
        deleted = []
        for vf in selected_versions:
            try:
                os.remove(os.path.join(version_folder, vf))
                deleted.append(vf)
            except Exception as e:
                st.error(f"Failed to delete {vf}: {e}")
        if deleted:
            st.success(f"Deleted: {', '.join(deleted)}")
        else:
            st.warning("No versions were deleted.")
else:
    st.info("No saved versions available for this file.")

# -------------------------------
# Borrar TODAS las versiones guardadas
# -------------------------------
st.markdown("---")
st.markdown("### 🧨 Delete All Versions (All Files)")

all_versions = [
    f for f in os.listdir(version_folder)
    if f.endswith(".txt")
]

if all_versions:
    if st.button("💣 Delete ALL Saved Versions (Irreversible)"):
        try:
            for f in all_versions:
                os.remove(os.path.join(version_folder, f))
            st.success("✅ All saved versions deleted.")
        except Exception as e:
            st.error(f"❌ Error deleting versions: {e}")
            
else:
    st.info("There are no saved versions in the system.")
    st.markdown("---")
import re

st.subheader("📤 Upload a Saved Version to Load")

uploaded_version = st.file_uploader("Upload a saved version (.txt)", type=["txt"], key="upload_saved_version")
manual_text = st.text_area("📋 Or paste the content manually", height=200, key="manual_upload_text")

# Variables para almacenar contenido y categoría detectada
version_content = None
base_name = None

if uploaded_version:
    filename = uploaded_version.name
    name_match = re.match(r"([A-Za-z]+)", filename)

    if name_match:
        base_name = name_match.group(1)

        if base_name in gachafile_options:
            version_content = uploaded_version.read().decode("utf-8")
            st.text_area(f"📄 Preview of '{filename}'", version_content, height=200, key="uploaded_version_preview", disabled=True)
        else:
            st.error(f"❌ Unknown file: '{base_name}' is not a valid gacha category.")
    else:
        st.error("❌ Invalid filename format. Use a file starting with the category name, like 'Item_*.txt'")

elif manual_text.strip():
    version_content = manual_text.strip()
    # Para contenido manual, el usuario debe elegir la categoría explícitamente.
    base_name = st.selectbox("📂 Assign content to category", options=gachafile_options, key="manual_category_select")
    st.text_area("📄 Preview of pasted content", version_content, height=200, key="manual_preview", disabled=True)

if version_content and base_name:
    if st.button(f"📥 Load to 'Saved Versions' as new version of '{base_name}'", key="load_uploaded_to_versions"):
        st.session_state.setdefault("gachafiles_versions", {}).setdefault(base_name, []).append(version_content)
        st.session_state.setdefault("edited_files", {})[base_name] = version_content
        if base_name not in st.session_state.get("original_files", {}):
            st.session_state.setdefault("original_files", {})[base_name] = version_content
        st.success(f"✅ Version added to saved history under '{base_name}' and updated as editable.")

st.markdown("---")
st.subheader("📊 Bell Curve Analysis")

# Inicialización del toggle en session_state
if "show_curve_analysis" not in st.session_state:
    st.session_state["show_curve_analysis"] = False

# Botón que activa/desactiva la visualización
if st.button("📈 Toggle Bell Curve Analysis"):
    st.session_state["show_curve_analysis"] = not st.session_state["show_curve_analysis"]

# Solo carga si está activado
if st.session_state["show_curve_analysis"]:
    st.markdown("""
    Customize how you want to visualize the expected rarity distributions and your actual results.
    """)

    col1, col2, col3 = st.columns(3)
    with col1:
        show_normal = st.checkbox("Show Normal Distribution", value=True)
    with col2:
        show_bonus = st.checkbox("Show Bonus Distribution", value=True)
    with col3:
        show_histogram = st.checkbox("Show Actual Pulls", value=True)

    sample_types = ["Ability", "Item", "Familiar", "Skill", "Trait"]
    sigma = 1.2
    skew_strength = 0.6
    bonus_chance = 0.0048
    bonus_max = 2.0

    def skewed_gauss(x, avg):
        skew = 1.0 + skew_strength if x > avg else 1.0 - skew_strength
        return np.exp(-((x - avg) ** 2) / (2 * sigma ** 2) * skew)

    df_log = pd.DataFrame(st.session_state.get("log", [])) if show_histogram else pd.DataFrame()

    if show_histogram and df_log.empty:
        st.info("No pulls have been made yet. Pull some results to enable histogram.")
    else:
        if show_histogram:
            if "Rarity" not in df_log.columns:
                st.warning("Rarity data is missing or log not initialized.")
                df_log = pd.DataFrame()
            else:
                df_log["Rarity"] = pd.to_numeric(df_log["Rarity"], errors="coerce")
                df_log = df_log.dropna(subset=["Rarity"])

        for pull_type in sample_types:
            x_vals = np.linspace(min_val, max_val, 500)
            df_base = pd.DataFrame({"Rarity": x_vals})

            charts = []

            if show_normal:
                df_base["Skewed"] = [skewed_gauss(x, avg) for x in x_vals]
                line_skewed = alt.Chart(df_base).mark_line(color="skyblue").encode(
                    x="Rarity",
                    y=alt.Y("Skewed", title="Weight (Normal)"),
                    tooltip=["Rarity", "Skewed"]
                ).properties(title=f"{pull_type} — Distribution")
                charts.append(line_skewed)

            if show_bonus:
                base_curve = np.array([skewed_gauss(x, avg) for x in x_vals])
                bonus_peak = np.array([
                    bonus_chance * np.exp(-((x - (avg + bonus_max / 2)) ** 2) / (2 * sigma ** 2))
                    for x in x_vals
                ])
                df_base["Bonus"] = base_curve + bonus_peak
                line_bonus = alt.Chart(df_base).mark_line(color="orange").encode(
                    x="Rarity",
                    y=alt.Y("Bonus", title="Weight (Bonus)"),
                    tooltip=["Rarity", "Bonus"]
                )
                charts.append(line_bonus)

            if show_histogram and not df_log.empty:
                pulls_type = df_log[df_log["Type"].str.lower() == pull_type.lower()]
                if not pulls_type.empty:
                    hist = alt.Chart(pulls_type).mark_bar(opacity=0.5, color="white").encode(
                        x=alt.X("Rarity", bin=alt.Bin(maxbins=25), title="Rarity"),
                        y=alt.Y("count()", title="Pull Count"),
                        tooltip=["count()"]
                    )
                    charts.append(hist)

            if charts:
                chart = alt.layer(*charts).resolve_scale(y='independent').interactive()
                st.altair_chart(chart, use_container_width=True)

# ------------------ PERSISTENT ROLL INVENTORY ------------------
st.markdown("---")
if "show_individual_inventory_toggle" not in st.session_state:
    st.session_state["show_individual_inventory_toggle"] = False

st.checkbox(
    "🎒 Individual Roll Inventory",
    key="show_individual_inventory_toggle",
)

if st.session_state["show_individual_inventory_toggle"]:
    try:
        inventory_instances = get_inventory()
        if inventory_instances:
            inventory_view = []
            for instance in inventory_instances:
                pull = instance.get("pull", {})
                inventory_view.append({
                    "ID": instance["id"],
                    "Status": instance.get("status", "stored"),
                    "Type": pull.get("Type", ""),
                    "Element": pull.get("Element", ""),
                    "Tier": pull.get("Tier", ""),
                    "Rarity": pull.get("Rarity", ""),
                })

            st.caption(
                "Each row is an individual pull. Repeated names remain separate "
                "instances with their own persistent IDs."
            )
            st.dataframe(
                pd.DataFrame(inventory_view),
                use_container_width=True,
                hide_index=True,
            )
            st.caption(f"Total individual instances: {len(inventory_view)}")

            st.markdown("### Equipment")
            st.caption(
                "Equip and unequip individual copies by ID. Only equipped "
                "instances are intended to affect character statistics."
            )
            # Level is derived from unique history rows; repeated pulls
            # count because each row represents a separate narrative event.
            character_pull_count = len(st.session_state.get("log", []))
            character_level = get_level_from_pulls(character_pull_count)
            slot_limit = get_equipment_slots(character_level)
            st.caption(
                f"Character level: {character_level} · "
                f"Pulls recorded: {character_pull_count}"
            )
            st.caption("Equipment limits are independent for each category.")
            slot_columns = st.columns(len(EQUIPMENT_CATEGORIES))
            for column, category in zip(slot_columns, EQUIPMENT_CATEGORIES):
                category_count = sum(
                    1 for instance in inventory_instances
                    if instance.get("status", "stored") == "equipped"
                    and str(instance.get("pull", {}).get("Type", "")).strip().casefold()
                    == category.casefold()
                )
                column.metric(category, f"{category_count}/{slot_limit}")

            selectable_instances = [
                instance for instance in inventory_instances
                if instance.get("status", "stored") in {"stored", "equipped"}
            ]
            if selectable_instances:
                instance_labels = {
                    instance["id"]: (
                        f"{instance.get('pull', {}).get('Element', 'Unknown')} "
                        f"— {instance.get('pull', {}).get('Type', '')} "
                        f"[{instance.get('status', 'stored')}] "
                        f"(ID: {instance['id'][:8]})"
                    )
                    for instance in selectable_instances
                }
                selected_roll_id = st.selectbox(
                    "Select an individual pull",
                    options=[instance["id"] for instance in selectable_instances],
                    format_func=lambda roll_id: instance_labels[roll_id],
                    key="selected_inventory_roll_id",
                )
                selected_instance = next(
                    instance for instance in selectable_instances
                    if instance["id"] == selected_roll_id
                )

                # Read-only inspection: viewing a pull never equips it or
                # regenerates its already-persisted modifiers.
                selected_pull = selected_instance.get("pull", {})
                with st.expander("🔎 Inspect selected pull", expanded=True):
                    st.markdown(f"**{selected_pull.get('Element', 'Unknown')}**")
                    st.caption(
                        f"{selected_pull.get('Type', 'Unknown')} · "
                        f"{selected_pull.get('Tier', 'Unknown')} · "
                        f"ID: {selected_instance['id']}"
                    )

                    random_modifiers = selected_instance.get("modifiers", [])
                    if random_modifiers:
                        modifier_rows = []
                        for modifier in random_modifiers:
                            kind = modifier.get("kind", "")
                            value = modifier.get("value", 0)
                            if kind == "percent":
                                formatted_value = f"+{float(value):.2f}%"
                                kind_label = "Percent"
                            elif kind == "flat":
                                formatted_value = f"+{float(value):.2f}"
                                kind_label = "Flat"
                            else:
                                formatted_value = str(value)
                                kind_label = str(kind)
                            modifier_rows.append({
                                "Stat": modifier.get("stat", "Unknown"),
                                "Modifier": kind_label,
                                "Value": formatted_value,
                            })
                        st.markdown("**Random generated modifiers**")
                        st.dataframe(
                            pd.DataFrame(modifier_rows),
                            use_container_width=True,
                            hide_index=True,
                        )
                    elif selected_instance.get("modifiers_generated"):
                        st.caption("This pull has no generated stat modifiers.")
                    elif selected_pull.get("Type") == "Item":
                        st.caption(
                            "Items are currently excluded from random stat modifiers."
                        )
                    else:
                        st.caption(
                            "No persisted random modifiers are available for this pull."
                        )

                    legacy_stats = {}
                    legacy_resistances = {}
                    for description_line in str(
                        selected_pull.get("Description", "")
                    ).splitlines():
                        if "#STATS" in description_line:
                            for stat, value in parse_stats(description_line).items():
                                legacy_stats[stat] = legacy_stats.get(stat, 0) + value
                        elif "#RESISTANCES" in description_line:
                            for resistance, value in parse_resistances(description_line).items():
                                legacy_resistances[resistance] = (
                                    legacy_resistances.get(resistance, 0) + value
                                )

                    if legacy_stats:
                        st.markdown("**Descriptive #STATS**")
                        st.dataframe(
                            pd.DataFrame([
                                {"Stat": stat, "Value": f"{value:+d}"}
                                for stat, value in legacy_stats.items()
                            ]),
                            use_container_width=True,
                            hide_index=True,
                        )

                    if legacy_resistances:
                        st.markdown("**Descriptive #RESISTANCES**")
                        st.dataframe(
                            pd.DataFrame([
                                {"Resistance": resistance, "Value": f"{value:+d}%"}
                                for resistance, value in legacy_resistances.items()
                            ]),
                            use_container_width=True,
                            hide_index=True,
                        )

                    has_star = (
                        str(selected_pull.get("Element", "")).lstrip().startswith("★")
                        or "boosted star bonus" in str(
                            selected_pull.get("Notes", "")
                        ).casefold()
                    )
                    if has_star:
                        if selected_instance.get("status") == "equipped":
                            st.success(
                                "★ Equipped star bonus: +5% to all final character stats."
                            )
                        else:
                            st.info(
                                "★ Star bonus: +5% to all final character stats "
                                "while this pull is equipped."
                            )

                    description = str(selected_pull.get("Description", "")).strip()
                    if description:
                        st.markdown("**Original description**")
                        st.text(description)

                selected_type = str(
                    selected_instance.get("pull", {}).get("Type", "")
                ).strip()
                action_col1, action_col2, action_col3 = st.columns(3)

                if selected_instance.get("status", "stored") == "equipped":
                    with action_col2:
                        if st.button("Unequip selected pull", key="unequip_selected_roll"):
                            try:
                                unequip_roll(selected_roll_id)
                                st.success("Pull returned to stored inventory.")
                                st.rerun()
                            except (InventoryStateError, ValueError) as error:
                                st.error(str(error))
                elif selected_type.casefold() not in {
                    category.casefold() for category in EQUIPMENT_CATEGORIES
                }:
                    st.info(
                        f"{selected_type or 'This category'} does not have "
                        "an equipment slot. Items remain in stored inventory."
                    )
                else:
                    with action_col1:
                        if st.button("Equip selected pull", key="equip_selected_roll"):
                            try:
                                equip_roll(
                                    selected_roll_id,
                                    int(character_level),
                                )
                                st.success("Pull equipped successfully.")
                                st.rerun()
                            except (InventoryStateError, ValueError) as error:
                                st.error(str(error))

                confirm_discard = st.checkbox(
                    "Confirm irreversible discard",
                    key=f"confirm_discard_{selected_roll_id}",
                )
                with action_col3:
                    if st.button(
                        "Discard selected pull",
                        key="discard_selected_roll",
                        disabled=not confirm_discard,
                    ):
                        try:
                            result = discard_roll(selected_roll_id, tracker)
                            if result["tp_awarded_now"]:
                                st.success(
                                    f"Discarded. +{result['tp_value']:.3f} TP awarded."
                                )
                            else:
                                st.success(
                                    "Discard state completed; TP for this ID was already recorded."
                                )
                            st.rerun()
                        except (InventoryStateError, ValueError) as error:
                            st.error(str(error))
            else:
                st.info("There are no stored or equipped instances to manage.")
        else:
            st.info("No individual pulls have been saved yet.")
    except InventoryDataError as error:
        st.error(str(error))

from character.character import Character
from character.validator import ValidationReport

st.markdown("---")
st.header("🧬 Character Builder Integration")

# Narrative level and stat-point allocation. Character attributes are never
# used by the gacha engine; only the pull history determines level.
character_pull_count = len(st.session_state.get("log", []))
level_progress = get_progress_to_next_level(character_pull_count)
character_level = level_progress["level"]
earned_stat_points = points_earned_for_level(character_level)

st.subheader("📈 Narrative Character Progression")
st.write(
    f"**Level {character_level}** · "
    f"{character_pull_count} documented pull(s)"
)
st.progress(
    level_progress["pulls_into_level"] / max(1, level_progress["pulls_for_this_level"])
)
st.caption(
    f"{level_progress['pulls_into_level']} / "
    f"{level_progress['pulls_for_this_level']} pulls toward level "
    f"{character_level + 1}. "
    f"Next level reward: +{character_level + 1} stat points."
)

try:
    progression_data = load_character_progress()
    allocated_total = sum(progression_data["allocated"].values())
    available_stat_points = earned_stat_points - allocated_total
    if available_stat_points < 0:
        st.warning(
            f"Your saved allocations exceed the points currently earned by "
            f"{abs(available_stat_points)}. They have been preserved; no "
            "additional points can be allocated until the history supports them."
        )
        available_stat_points = 0

    point_col1, point_col2 = st.columns(2)
    point_col1.metric("Stat points earned", earned_stat_points)
    point_col2.metric("Available to allocate", available_stat_points)

    with st.expander("🧮 Allocate character stat points", expanded=available_stat_points > 0):
        allocation_stat = st.selectbox(
            "Choose a stat",
            options=list(STAT_NAMES),
            key="progression_stat_choice",
        )
        allocation_amount = st.number_input(
            "Points to allocate",
            min_value=1,
            max_value=max(1, available_stat_points),
            value=1,
            step=1,
            disabled=available_stat_points <= 0,
            key="progression_stat_amount",
        )
        if st.button(
            "Save stat allocation",
            disabled=available_stat_points <= 0,
            key="save_progression_allocation",
        ):
            try:
                allocate_stat_points(
                    allocation_stat,
                    int(allocation_amount),
                    character_pull_count,
                )
                st.success(
                    f"Allocated {allocation_amount} point(s) to {allocation_stat}."
                )
                st.rerun()
            except ValueError as error:
                st.error(str(error))

    st.caption("Current level-up allocations")
    st.dataframe(
        pd.DataFrame([
            {"Stat": stat, "Allocated": value}
            for stat, value in progression_data["allocated"].items()
        ]),
        use_container_width=True,
        hide_index=True,
    )
except ValueError as error:
    st.error(f"Character progression could not be loaded: {error}")

if st.button("🧪 Generate Character From Gacha"):
    report = ValidationReport()
    char = Character()

    char.load_free_categories("characterfiles", report)

    try:
        data = char.build()
    except InventoryDataError as error:
        st.error(f"Unable to load equipped inventory: {error}")
    else:
        st.subheader("📌 Final Stats")
        st.json(data["stats"])

        st.subheader("🔥 Resistances")
        st.json(data["resistances"])

        st.subheader("📚 Additional Fields")
        st.json(data["fields"])

        st.markdown("---")
        st.subheader("🛠 Validation Report")
        st.json(report.to_dict())
