import streamlit as st
import plotly.graph_objects as go
import numpy as np
import pandas as pd
import re
import concurrent.futures
import plotly.colors
import os

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
    """解析 .raw 或 .imp 文件，提取数据，同时支持新旧两种格式"""
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
    file_format = "old"  # 默认假设为旧格式
    
    # 检查是否为新格式
    if any("{Start _FULL data}" in line for line in lines):
        file_format = "new"
    
    if file_format == "new":
        in_statistics = False
        in_individual_data = False
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # 识别数据块边界
            if line == "{Start _FULL data}":
                continue
            elif line == "{***Begin_Statistics***}":
                in_statistics = True
                continue
            elif line == "{***End_Statistics***}":
                in_statistics = False
                continue
            elif line == "{***Begin_Individual_Element_Data***}":
                in_individual_data = True
                continue
                
            # 识别 section
            section_match = re.match(r"^\[\s*(.+?)\s*\]$", line)
            if section_match:
                current_section = section_match.group(1).strip()
                # 移除新格式中的后缀，使其与旧格式兼容
                current_section = re.sub(r"_FULL(\s+\([^\)]+\))?", "", current_section)
                sections[current_section] = {"index_value": [], "waveform": [], "raw_text": []}
                continue

            # 识别坏点 BadEL
            if "BadEL" in line or "Bad_Elements" in line:
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
                    
            # 从新格式的Header_FULL中提取信息
            if current_section == "Header_FULL":
                key_value_match = re.match(r"^(\w+)\s*=\s*(.+)", line)
                if key_value_match:
                    key, value = key_value_match.groups()
                    # 将新格式的部分字段映射到旧格式的字段
                    if key == "SerialNumber":
                        header["SN"] = value
                    elif key == "TestStation":
                        header["TestStation"] = value
                    elif key == "Operator":
                        header["Operator"] = value
                    elif key == "Date":
                        header["Date"] = value
                    elif key == "Time":
                        header["Time"] = value
                    else:
                        header[key] = value
                        
            # 提取新格式中的测试结果
            if current_section == "Probe_Status_FULL":
                status_match = re.match(r"Overall_Status\s*=\s*(PASS|FAIL)", line, re.IGNORECASE)
                if status_match:
                    header["ResultStatus"] = status_match.group(1).upper()
                    
    else:  # 旧格式处理逻辑（保持原有代码不变）
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
        header["file_format"] = file_format

    # 提取 Probe_Status 中的测试结果字段（PASS / FAIL） - 旧格式逻辑
    if "ResultStatus" not in header:
        for line in lines:
            if "[Probe_Status]" in line:
                current_section = "Probe_Status"
                continue
            if current_section == "Probe_Status":
                status_match_raw = re.match(r"Overall_Status\s*=\s*(PASS|FAIL)", line, re.IGNORECASE)
                status_match_imp = re.match(r"PassOrFail\s*=\s*(Pass|Fail)", line, re.IGNORECASE)
                if status_match_raw:
                    header["ResultStatus"] = status_match_raw.group(1).upper()
                elif status_match_imp:
                    header["ResultStatus"] = status_match_imp.group(1).upper()

    return file_name, sections, header

def calculate_summary(data_array, upper_limit=None, lower_limit=None):
    """计算数据的统计摘要"""
    if len(data_array) == 0:
        return {}
    
    summary = {
        'Count': len(data_array),
        'Average': np.mean(data_array),
        'Min': np.min(data_array),
        'Max': np.max(data_array),
        'Range': np.max(data_array) - np.min(data_array),
        'Std Dev': np.std(data_array)
    }
    
    # 计算符合规格的比例
    if upper_limit is not None and lower_limit is not None:
        within_spec = np.sum((data_array >= lower_limit) & (data_array <= upper_limit))
        summary['Within Spec (%)'] = (within_spec / len(data_array)) * 100 if len(data_array) > 0 else 0
        summary['Above UL (%)'] = (np.sum(data_array > upper_limit) / len(data_array)) * 100
        summary['Below LL (%)'] = (np.sum(data_array < lower_limit) / len(data_array)) * 100
    
    return summary

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
                      
    result_statuses = list(set(h.get("ResultStatus", "Unknown") for h in header_info))
    selected_status = st.sidebar.selectbox("PASS or Fail？", ["All"] + result_statuses)

    filtered_files = [
        h["file_name"]
        for h in header_info
        if (selected_station == "All" or h.get("TestStation") == selected_station)
        and (selected_operator == "All" or h.get("Operator") == selected_operator)
        and (selected_status == "All" or h.get("ResultStatus") == selected_status)
    ]

    # 🆕 生成文件名前缀（去掉路径、后缀，并提取 "-" 前的部分）
    file_name_prefix_map = {}
    for fn in filtered_files:
        base_name = os.path.splitext(fn)[0]  # 去掉 .raw/.imp 后缀
        prefix = base_name.split("-")[0]  # 提取 "-" 前缀
        file_name_prefix_map.setdefault(prefix, []).append(fn)  # 一个前缀可能对应多个文件

    # 🆕 显示文件名前缀选项
    file_prefix_options = sorted(file_name_prefix_map.keys())
    selected_prefixes = st.sidebar.multiselect("指定SN？", ["All"] + file_prefix_options, default=["All"])

    # 🧠 更新 filtered_files（按前缀筛选）
    if "All" not in selected_prefixes:
        filtered_files = []
        for prefix in selected_prefixes:
            filtered_files.extend(file_name_prefix_map.get(prefix, []))
                                    
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

    with tab2:
        for section in selected_sections:
            data_sets = sections_data.get(section, [])
            if not data_sets:
                continue

            file_rows = []
            for file_name, data in data_sets:
                if file_name not in filtered_files:
                    continue

                index_value_data = data.get("index_value", [])
                if not index_value_data:
                    continue

                try:
                    values = np.array(index_value_data)[:, 1].astype(float)
                except Exception:
                    continue

                if values.size == 0:
                    continue

                stats = calculate_summary(values, upper_limit, lower_limit)

                count_total = values.size

                count_above = np.sum(values > upper_limit) if upper_limit is not None else 0
                count_below = np.sum(values < lower_limit) if lower_limit is not None else 0

                above_percent = (count_above / count_total) * 100 if count_total > 0 else 0
                below_percent = (count_below / count_total) * 100 if count_total > 0 else 0

                above_display = f"{count_above} ({above_percent:.1f}%)" if upper_limit is not None else "-"
                below_display = f"{count_below} ({below_percent:.1f}%)" if lower_limit is not None else "-"

                file_header = next((h for h in header_info if h["file_name"] == file_name), {})
                short_name = os.path.splitext(file_name)[0]

                row = {
                    "File": short_name,
                    "Station": file_header.get("TestStation") or file_header.get("Station") or "未知",
                    "Operator": file_header.get("Operator", "未知"),
                    "TestTime": f"{file_header.get('Date', '未知')} {file_header.get('Time', '')}",
                    "Status": file_header.get("ResultStatus", "未知"),
                    "ElementCount": count_total,
                    "Average": round(stats.get('Average', 0), 4),
                    "Min": round(stats.get('Min', 0), 4),
                    "Max": round(stats.get('Max', 0), 4),
                    "Range": round(stats.get('Range', 0), 4),
                    "Std": round(stats.get('Std Dev', 0), 4),
                }

                if upper_limit is not None:
                    row["超上限"] = above_display
                if lower_limit is not None:
                    row["低下限"] = below_display

                file_rows.append(row)

            if file_rows:
                df_summary = pd.DataFrame(file_rows)

                with st.expander(f"📊 {section} 的统计摘要", expanded=False):
                    # 先显示统计表
                    st.dataframe(df_summary, use_container_width=True)

                    # 再绘制图表（和之前逻辑一样）
                    fig = go.Figure()

                    # 添加上下限线
                    if upper_limit is not None:
                        fig.add_hline(y=upper_limit, line=dict(color="red", dash="dash"),
                                      annotation_text="Upper Limit", annotation_position="top left")

                    if lower_limit is not None:
                        fig.add_hline(y=lower_limit, line=dict(color="blue", dash="dash"),
                                      annotation_text="Lower Limit", annotation_position="bottom left")

                    for file_name, data in data_sets:
                        if file_name not in filtered_files:
                            continue

                        index_value_data = data.get("index_value", [])
                        if not index_value_data:
                            continue

                        index_value_array = np.array(index_value_data)
                        x = index_value_array[:, 0]
                        y = index_value_array[:, 1].astype(float)

                        file_header = next((h for h in header_info if h["file_name"] == file_name), {})
                        station = file_header.get("TestStation") or file_header.get("Station") or "Unknown"
                        color = color_map.get(station, "gray")

                        fig.add_trace(go.Scatter(
                            x=x, y=y,
                            mode='markers+lines',
                            marker=dict(size=4),
                            line=dict(width=0.6, color=color),
                            name=station,
                            hoverinfo='text',
                            hovertext=[f"File: {file_name}<br>Station: {station}<br>Index: {xi}<br>Value: {yi}"
                                       for xi, yi in zip(x, y)],
                        ))

                    if len(fig.data) > 0:
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
