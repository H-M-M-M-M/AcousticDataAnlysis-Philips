import streamlit as st
import matplotlib.pyplot as plt
import numpy as np
import re

# 📌 Streamlit 页面设置
st.set_page_config(page_title="RAW & IMP 数据分析", layout="wide")
st.title("📊 RAW & IMP 数据分析可视化")

# 侧边栏 - 文件上传
st.sidebar.header("📂 上传你的文件")
uploaded_files = st.sidebar.file_uploader(
    "选择 .raw 或 .imp 文件", type=["raw", "imp"], accept_multiple_files=True
)

# 存储所有文件的 section 数据
sections_data = {}
bad_elements = set()

if uploaded_files:
    for file in uploaded_files:
        file_name = file.name

        # 读取文件
        try:
            lines = file.read().decode("utf-8").splitlines()
        except UnicodeDecodeError:
            lines = file.read().decode("latin-1").splitlines()

        # 解析数据
        sections = {}
        current_section = None

        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 1️⃣ **匹配 `[]` 标题**
            section_match = re.match(r"^\[\s*(.+?)\s*\]$", line)
            if section_match:
                current_section = section_match.group(1).strip()
                sections[current_section] = {"index_value": [], "waveform": [], "raw_text": []}
                continue

            # 2️⃣ **BadEL 处理**（如果 `[Header]` 中有 BadEL 关键字，跳过）
            if "BadEL" in line:
                bad_elements.add(current_section)

            # 3️⃣ **匹配 index=value 形式**
            data_match = re.match(r"^\s*(\d+)\s*=\s*(-?[\d.]+)", line)
            if data_match and current_section:
                key = int(data_match.group(1))
                value = float(data_match.group(2))
                sections[current_section]["index_value"].append((key, value))

            # 4️⃣ **匹配 Waveform.Array**（处理带单位的情况）
            waveform_match = re.match(r"^Waveform\.Array\s*=\s*(.+)", line)
            if waveform_match and current_section:
                raw_values = waveform_match.group(1).split(",")
                cleaned_values = []
                for v in raw_values:
                    num_match = re.search(r"-?[\d.]+", v)
                    if num_match:
                        cleaned_values.append(float(num_match.group(0)))
                sections[current_section]["waveform"] = cleaned_values

            # 5️⃣ **存储 Header 其他数据**
            if current_section and "=" in line:
                sections[current_section]["raw_text"].append(line)

        # 存储数据
        for section, data in sections.items():
            if section in bad_elements:  # 🛑 **跳过 BadEL**
                continue
            if section not in sections_data:
                sections_data[section] = []
            sections_data[section].append((file_name, data))

    # 获取所有 section
    all_sections = [sec for sec in sections_data.keys() if sections_data[sec]]  # 去除空 sections

    # 侧边栏 - 选择要显示的部分
    selected_sections = st.sidebar.multiselect("选择要绘制的部分", all_sections, default=all_sections)

    # 使用 Tabs 分离不同内容
    tab1, tab2 = st.tabs(["📄 Header 信息", "📊 数据图表"])

    # 🔹 **Header 信息展示**
    with tab1:
        for section in selected_sections:
            if section.lower() == "header":
                for file_name, data in sections_data[section]:
                    st.subheader(f"📄 Header 信息 - {file_name}")
                    st.code("\n".join(data["raw_text"]), language="ini")
    
    # 🔹 **绘制数据图**
    with tab2:
        for section in selected_sections:
            data_sets = sections_data.get(section, [])
            if not data_sets:
                continue

            # 📉 **处理 Waveform.Array**
            if section.isdigit():
                fig, ax = plt.subplots(figsize=(8, 4))
                for file_name, data in data_sets:
                    waveform = data["waveform"]
                    if waveform:
                        x = np.arange(len(waveform))
                        y = np.array(waveform)
                        ax.plot(x, y, marker='', linestyle='-', label=f"{file_name}", linewidth=1)
                if len(ax.lines) > 0:
                    ax.set_xlabel("Sample Index")
                    ax.set_ylabel("Amplitude")
                    ax.set_title(f"Waveform Plot - {section}")
                    ax.legend()
                    ax.grid(True)
                    st.pyplot(fig)
                continue

            # 📊 **处理 index=value 数据**
            fig, ax = plt.subplots(figsize=(8, 4))
            for file_name, data in data_sets:
                index_value_data = data["index_value"]
                if index_value_data:
                    x, y = zip(*sorted(index_value_data))
                    ax.plot(x, y, marker='o', linestyle='-', label=f"{file_name}", linewidth=1)
            if len(ax.lines) > 0:
                ax.set_xlabel("Index")
                ax.set_ylabel("Value")
                ax.set_title(f"Scatter Plot - {section}")
                ax.legend()
                ax.grid(True)
                st.pyplot(fig)
