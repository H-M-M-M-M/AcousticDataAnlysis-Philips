import streamlit as st
import plotly.graph_objects as go
import numpy as np
import re

# 📌 Streamlit 页面设置
st.set_page_config(page_title="RAW & IMP 数据分析", layout="wide")
st.title("📊 RAW & IMP 数据分析可视化")

# 侧边栏 - 文件上传
st.sidebar.header("📂 上传你的文件")
uploaded_files = st.sidebar.file_uploader("选择 .raw 或 .imp 文件", type=["raw", "imp"], accept_multiple_files=True)

# 存储所有文件的 section 数据
sections_data = {}
bad_elements = set()

if uploaded_files:
    for file in uploaded_files:
        file_name = file.name
        try:
            lines = file.read().decode("utf-8").splitlines()
        except UnicodeDecodeError:
            lines = file.read().decode("latin-1").splitlines()

        sections = {}
        current_section = None
        for line in lines:
            line = line.strip()
            if not line:
                continue

            section_match = re.match(r"^\[\s*(.+?)\s*\]$", line)
            if section_match:
                current_section = section_match.group(1).strip()
                sections[current_section] = {"index_value": [], "waveform": [], "raw_text": []}
                continue

            if "BadEL" in line:
                bad_elements.add(current_section)

            data_match = re.match(r"^\s*(\d+)\s*=\s*(-?[\d.]+)", line)
            if data_match and current_section:
                key = int(data_match.group(1))
                value = float(data_match.group(2))
                sections[current_section]["index_value"].append((key, value))

            waveform_match = re.match(r"^Waveform\.Array\s*=\s*(.+)", line)
            if waveform_match and current_section:
                raw_values = waveform_match.group(1).split(",")
                cleaned_values = [float(re.search(r"-?[\d.]+", v).group(0)) for v in raw_values if re.search(r"-?[\d.]+", v)]
                sections[current_section]["waveform"] = cleaned_values

            if current_section and "=" in line:
                sections[current_section]["raw_text"].append(line)

        for section, data in sections.items():
            if section in bad_elements:
                continue
            if section not in sections_data:
                sections_data[section] = []
            sections_data[section].append((file_name, data))

    all_sections = [sec for sec in sections_data.keys() if sections_data[sec]]
    selected_sections = st.sidebar.multiselect("选择要绘制的部分", all_sections, default=all_sections)

    tab1, tab2 = st.tabs(["📄 Header 信息", "📊 数据图表"])

    with tab1:
        for section in selected_sections:
            if section.lower() == "header":
                for file_name, data in sections_data[section]:
                    st.subheader(f"📄 Header 信息 - {file_name}")
                    st.code("\n".join(data["raw_text"]), language="ini")
    
    with tab2:
        for section in selected_sections:
            data_sets = sections_data.get(section, [])
            if not data_sets:
                continue

            fig = go.Figure()
            has_data = False
            for file_name, data in data_sets:
                index_value_data = data["index_value"]
                if index_value_data:
                    x, y = zip(*sorted(index_value_data))
                    hover_text = [f"File: {file_name}<br>Index: {xi}<br>Value: {yi}" for xi, yi in zip(x, y)]
                    fig.add_trace(go.Scatter(x=x, y=y, mode='markers+lines', line=dict(width=1), name=file_name, hovertext=hover_text, hoverinfo='text'))
                    has_data = True
            
            if has_data:
                fig.update_layout(
                    title=f"Scatter Plot - {section}",
                    xaxis_title="Index",
                    yaxis_title="Value",
                    template="plotly_white"
                )
                st.plotly_chart(fig)
