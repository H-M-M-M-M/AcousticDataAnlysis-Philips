import streamlit as st
import plotly.graph_objects as go
import numpy as np
import pandas as pd
import re
import concurrent.futures
import plotly.colors

# 📌 Streamlit 页面设置
st.set_page_config(page_title="RAW & IMP 数据分析", layout="wide")
st.title("📊 RAW & IMP 数据分析可视化，直接从网盘导入APE和/或MIMS数据就可以啦⛏")

# 侧边栏 - 文件上传
st.sidebar.header("📂 上传你的文件")
uploaded_files = st.sidebar.file_uploader("选择 .raw 或 .imp 文件", type=["raw", "imp"], accept_multiple_files=True)

# 存储所有文件的 section 数据
sections_data = {}
bad_elements = set()
header_info = []
color_map = {}  # 用于存储 Station 对应的颜色

def parse_file(file):
    """解析 .raw 或 .imp 文件，提取数据"""
    file_name = file.name
    try:
        lines = file.read().decode("utf-8").splitlines()
    except UnicodeDecodeError:
        try:
            lines = file.read().decode("latin-1").splitlines()
        except UnicodeDecodeError:
            lines = file.read().decode("gbk").splitlines()  # 兼容 GBK

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

        # 存储 Header 信息（保留完整格式）
        if current_section == "Header":
            key_value_match = re.match(r"^(\w+)\s*=\s*(.+)", line)
            if key_value_match:
                key, value = key_value_match.groups()
                header[key] = value  # 直接存储，不修改格式

    if header:
        header["file_name"] = file_name

    return file_name, sections, header

if uploaded_files:
    # 使用多线程并行解析文件，提高解析速度
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

        # 分配颜色
        station = header.get("TestStation") or header.get("Station") or "Unknown"
        if station not in color_map:
            color_palette = plotly.colors.qualitative.Plotly  # 使用高对比度调色板
            color_index = len(color_map) % len(color_palette)  # 循环使用颜色
            color_map[station] = color_palette[color_index]  # 存储颜色

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
   
   # 用户自定义 limit line
    st.sidebar.markdown("### ➕ 添加 Limit Lines（添加单点spec，一次加一张图）")
    upper_limit = st.sidebar.number_input("设置上限（Upper Limit）", value=None, format="%.4f", step=0.1)
    lower_limit = st.sidebar.number_input("设置下限（Lower Limit）", value=None, format="%.4f", step=0.1)

    # 获取所有有效 sections
    all_sections = [sec for sec, data in sections_data.items() if data]
    selected_sections = st.sidebar.multiselect("选择要绘制的部分", all_sections, default=all_sections)
    
    # 创建两个 Tab 页面
    tab1, tab2 = st.tabs(["📄 Header 信息", "📊 数据图表"])
                
    # 📄 Header 信息展示
    with tab1:
        header_df = {}
        for header in header_info:
            file_name = header["file_name"]
            if file_name in filtered_files:
                for key, value in header.items():
                    if key != "file_name":  # 排除文件名
                        header_df.setdefault(key, []).append(value)

        # 确保所有列的长度一致
        max_length = max(len(v) for v in header_df.values())
        for key in list(header_df.keys()):
            header_df[key] += [None] * (max_length - len(header_df[key]))  # 填充缺失值

        st.write(pd.DataFrame(header_df))  # 显示为表格

    # 📊 数据可视化
    with tab2:
        has_valid_data = False
        for section in selected_sections:
            data_sets = sections_data.get(section, [])
            if not data_sets:
                continue
            fig = go.Figure()
            # 添加上下限线（如果用户设置了）
            if upper_limit is not None:
                fig.add_hline(y=upper_limit, line=dict(color="red", dash="dash"), 
                            annotation_text="Upper Limit", annotation_position="top left")

            if lower_limit is not None:
                fig.add_hline(y=lower_limit, line=dict(color="blue", dash="dash"), 
                            annotation_text="Lower Limit", annotation_position="bottom left")                  

            for file_name, data in data_sets:
                if file_name not in filtered_files:
                    continue  # 只绘制符合筛选条件的文件

                index_value_data = data["index_value"]
                if index_value_data:
                    index_value_array = np.array(index_value_data)
                    x = index_value_array[:, 0]  # Index
                    y = index_value_array[:, 1]  # Value

                    # 获取对应的 Station 并分配颜色
                    file_header = next((h for h in header_info if h["file_name"] == file_name), {})
                    station = file_header.get("TestStation") or file_header.get("Station") or "Unknown"
                    color = color_map.get(station, "gray")  # 默认灰色
                    color_with_alpha = color.replace('rgba', 'rgba(0.6)')  # 适当降低透明度

                    # 添加曲线到图表
                    fig.add_trace(go.Scatter(
                        x=x, y=y, 
                        mode='markers+lines', 
                        marker=dict(size=4),  # 设置点的大小
                        line=dict(width=0.6, color=color_with_alpha),  # 设置线条宽度
                        name=station,  # 显示 Station 名称
                        hoverinfo='text',
                        hovertext=[f"File: {file_name}<br>Station: {station}<br>Index: {xi}<br>Value: {yi}" 
                        for xi, yi in zip(x, y)],
                    ))

            if len(fig.data) > 0:  # 检查是否有数据
                fig.update_layout(
                    title=f"Scatter Plot - {section}",
                    xaxis_title="Element",
                    yaxis_title="Value",
                    template="plotly_white",
                    showlegend=True,
                )
                st.plotly_chart(fig, use_container_width=True)
                has_valid_data = True

        if not has_valid_data:
            st.warning("⚠️ 没有符合筛选条件的数据可视化。")
