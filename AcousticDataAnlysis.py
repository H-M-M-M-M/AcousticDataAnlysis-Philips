import streamlit as st
import plotly.graph_objects as go
import numpy as np
import re
import concurrent.futures

# 📌 Streamlit 页面设置
st.set_page_config(page_title="RAW & IMP 数据分析", layout="wide")
st.title("📊 RAW & IMP 数据分析可视化")

# 侧边栏 - 文件上传
st.sidebar.header("📂 上传你的文件")
uploaded_files = st.sidebar.file_uploader("选择 .raw 或 .imp 文件", type=["raw", "imp"], accept_multiple_files=True)

# 清除文件按钮
#if st.sidebar.button("❌ 清除所有文件"):
   # st.session_state["uploaded_files"] = []
   # st.rerun()

# 存储所有文件的 section 数据
sections_data = {}
bad_elements = set()
header_info = []


def parse_file(file):
    """解析 .raw 或 .imp 文件，提取数据"""
    file_name = file.name
    try:
        lines = file.read().decode("utf-8").splitlines()
    except UnicodeDecodeError:
        lines = file.read().decode("latin-1").splitlines()

    sections = {}
    current_section = None
    header = {}

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 识别 section
        section_match = re.match(r"^\[\s*(.+?)\s*\]$", line)
        if section_match:
            current_section = section_match.group(1).strip()
            sections[current_section] = {"index_value": [], "waveform": [], "raw_text": []}
            continue

        # 识别坏点 BadEL
        if "BadEL" in line:
            bad_elements.add(current_section)

        # 解析键值对数据（去除单位）
        data_match = re.match(r"^\s*(\d+)\s*=\s*([\d.-]+)", line)
        if data_match and current_section:
            key = int(data_match.group(1))
            value = float(re.search(r"-?[\d.]+", data_match.group(2)).group(0))  # 仅提取数值部分
            sections[current_section]["index_value"].append((key, value))

        # 解析 Waveform 数组（去除单位）
        waveform_match = re.match(r"^Waveform\.Array\s*=\s*(.+)", line)
        if waveform_match and current_section:
            raw_values = waveform_match.group(1).split(",")
            cleaned_values = [
                float(re.search(r"-?[\d.]+", v).group(0)) for v in raw_values if re.search(r"-?[\d.]+", v)
            ]
            sections[current_section]["waveform"] = cleaned_values

        # 存储 Header 信息
        if current_section == "Header" and "=" in line:
            sections[current_section]["raw_text"].append(line)
            key_value_match = re.match(r"^(\w+)\s*=\s*(.+)", line)
            if key_value_match:
                key, value = key_value_match.groups()
                if key in ["TestStation", "Operator"]:
                    header[key] = value

    if header:
        header["file_name"] = file_name

    return file_name, sections, header


if uploaded_files:
    # 使用多线程并行解析文件，加快速度
    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = list(executor.map(parse_file, uploaded_files))

    for file_name, sections, header in results:
        if header:
            header_info.append(header)

        # 处理 sections 数据
        for section, data in sections.items():
            if section in bad_elements:
                continue  # 跳过坏点数据
            sections_data.setdefault(section, []).append((file_name, data))

    # 获取 TestStation 和 Operator 可选项
    test_stations = list(set(h["TestStation"] for h in header_info if "TestStation" in h))
    operators = list(set(h["Operator"] for h in header_info if "Operator" in h))

    # 侧边栏筛选 TestStation 和 Operator
    selected_station = st.sidebar.selectbox("筛选 TestStation", ["All"] + test_stations)
    selected_operator = st.sidebar.selectbox("筛选 Operator", ["All"] + operators)

    # 根据筛选条件获取符合的文件名
    filtered_files = [h["file_name"] for h in header_info if
                      (selected_station == "All" or h.get("TestStation") == selected_station) and
                      (selected_operator == "All" or h.get("Operator") == selected_operator)]

    # 获取所有有效 sections
    all_sections = [sec for sec, data in sections_data.items() if data]
    selected_sections = st.sidebar.multiselect("选择要绘制的部分", all_sections, default=all_sections)

    # 创建两个 Tab 页面
    tab1, tab2 = st.tabs(["📄 Header 信息", "📊 数据图表"])

    # 📄 Header 信息展示
    with tab1:
        for header in header_info:
            if header["file_name"] in filtered_files:
                st.subheader(f"📄 Header 信息 - {header['file_name']}")
                header_text = "\n".join(next((data["raw_text"] for _, data in sections_data.get("Header", []) if "raw_text" in data), []))
                st.code(header_text, language="ini")

    # 📊 数据可视化
    with tab2:
        has_valid_data = False  # 用于判断是否有数据
        for section in selected_sections:
            data_sets = sections_data.get(section, [])
            if not data_sets:
                continue

            fig = go.Figure()
            section_has_data = False  # 该 section 是否有数据

            for file_name, data in data_sets:
                if file_name not in filtered_files:
                    continue  # 只绘制符合筛选条件的文件

                index_value_data = data["index_value"]
                if index_value_data:
                    x, y = zip(*sorted(index_value_data))
                    hover_text = [f"File: {file_name}<br>Index: {xi}<br>Value: {yi}" for xi, yi in zip(x, y)]
                    fig.add_trace(go.Scatter(x=x, y=y, mode='markers+lines', line=dict(width=1),
                                             name=f"{file_name} - {section}",
                                             hovertext=hover_text, hoverinfo='text'))
                    section_has_data = True
                    has_valid_data = True  # 至少有一个 section 有数据

            if section_has_data:
                fig.update_layout(
                    title=f"Scatter Plot - {section}",
                    xaxis_title="Element",
                    yaxis_title="Value",
                    template="plotly_white"
                )
                st.plotly_chart(fig)

        # 如果没有任何数据，则不显示图表
        if not has_valid_data:
            st.warning("⚠️ 没有符合筛选条件的数据可视化。")
