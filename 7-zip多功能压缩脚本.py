#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
7-Zip 多功能压缩工具集 - 终极全功能删源+调等+全模态明细版
1. 支持【当前目录】与【外部文件列表(txt)】双模操作
2. 1~10 模式完美支持“压缩后自动切除源文件”联动，释放硬盘空间
3. 核心升级：A、B、C 单元全模态完美支持「待处理项目列表明细及总大小汇总显示」
4. 核心升级：压缩失败时自动抓取并输出 7-Zip 底层原生报错原因，方便排查
5. 全自动接入 -bsp1 参数，显示 7-Zip 原生真实压缩进度
"""

import os
import subprocess
import sys
import re
import shutil
from pathlib import Path

# 强制将工作目录锁定为脚本所在文件夹
os.chdir(Path(__file__).parent.resolve())

# ================= 自动高速安装官方原生 tqdm 并即时加载 =================
try:
    from tqdm import tqdm
except ImportError:
    print("💡 检测到未安装 tqdm 进度条库，正在通过清华源自动安装原生标准库...")
    # 调用官方 pip 从清华镜像站高速下载安装官方标准包
    ret = os.system(f'"{sys.executable}" -m pip install tqdm -i https://pypi.tuna.tsinghua.edu.cn/simple')
    
    if ret == 0:
        try:
            # 刷新系统模块路径缓存，确保新装的官方标准库能立即被当前进程读取
            import site
            import importlib
            importlib.invalidate_caches()
            from tqdm import tqdm
            print("✅ 官方原生 tqdm 库安装成功，已成功载入！\n")
        except ImportError:
            tqdm = None
    else:
        tqdm = None

    # 仅在无网络导致官方库安装彻底失败时，作为备用防闪退垫底
    if tqdm is None:
        print("⚠️ 官方库下载失败（可能当前无网络连接），已切入纯文本兼容模式运行。\n")
        class DummyTqdm:
            def __init__(self, *args, **kwargs):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def update(self, *args, **kwargs):
                pass
            def set_description(self, *args, **kwargs):
                pass
        tqdm = DummyTqdm
# ==============================================================================
    from tqdm import tqdm

def strip_quotes(s):
    """去除字符串首尾的单引号或双引号"""
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    if s.startswith("'") and s.endswith("'"):
        return s[1:-1]
    return s
    
def format_size(size_bytes):
    """将字节大小转换为易读的格式 (KB, MB, GB)"""
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)
    while size >= 1024.0 and i < len(size_names) - 1:
        size /= 1024.0
        i += 1
    if i == 0:
        return f"{int(size)} {size_names[i]}"
    elif size < 10:
        return f"{size:.2f} {size_names[i]}"
    elif size < 100:
        return f"{size:.1f} {size_names[i]}"
    else:
        return f"{int(size)} {size_names[i]}"

def get_item_size(item_path):
    """安全获取文件或文件夹大小"""
    try:
        if not os.path.exists(item_path):
            return 0
        if os.path.isfile(item_path):
            return os.path.getsize(item_path)
        elif os.path.isdir(item_path):
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(item_path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    try:
                        total_size += os.path.getsize(filepath)
                    except (OSError, IOError):
                        continue
            return total_size
        else:
            return os.path.getsize(item_path)
    except (OSError, IOError):
        return 0

def parse_7zip_progress(line):
    """解析7-Zip的输出，提取进度百分比"""
    percent_match = re.search(r'(\d+)%', line)
    if percent_match:
        return int(percent_match.group(1))
    return None

class MultiCompressor:
    def __init__(self, sevenzip_path, compress_level=5):
        self.sevenzip = sevenzip_path
        self.compress_level = compress_level
        if not os.path.exists(self.sevenzip):
            raise FileNotFoundError(f"7-Zip程序不存在: {self.sevenzip}")
    
    def compress_with_real_progress(self, source_path, target_path, target_format, item_name, item_type="文件"):
        """使用7-Zip压缩并显示真实进度，失败时捕获原生错误详情"""
        try:
            if os.path.isdir(source_path):
                cmd = [
                    self.sevenzip, 'a', f'-t{target_format}', str(target_path),
                    str(source_path), f'-mx={self.compress_level}', '-r', '-bsp1'
                ]
            else:
                cmd = [
                    self.sevenzip, 'a', f'-t{target_format}', str(target_path),
                    str(source_path), f'-mx={self.compress_level}', '-bsp1'
                ]
            
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     universal_newlines=True, bufsize=1, creationflags=subprocess.CREATE_NO_WINDOW)
            
            # 建立错误日志缓冲池
            output_logs = []
            with tqdm(total=100, desc=f"压缩{item_type}: {item_name[:25]:25}", position=1, leave=False, unit="%") as pbar:
                last_progress = 0
                for line in process.stdout:
                    output_logs.append(line)  # 实时记录输出日志
                    progress = parse_7zip_progress(line)
                    if progress is not None and progress > last_progress:
                        pbar.update(progress - last_progress)
                        last_progress = progress
                        pbar.set_description(f"压缩{item_type}: {item_name[:25]:25} ({progress}%)")
                process.wait()
                
                if process.returncode == 0:
                    pbar.update(100 - last_progress)
                    pbar.set_description(f"✓ 完成: {item_name[:25]:25}")
                    return True
                else:
                    pbar.set_description(f"✗ 失败: {item_name[:25]:25}")
                    # 打印7-Zip原生失败原因
                    print(f"\n\n❌ [排查报告] {item_type} 【{item_name}】 封包失败！")
                    print("------------------- 7-Zip 原生错误日志 -------------------")
                    error_content = [l.strip() for l in output_logs if l.strip() and "%" not in l and "Compressing" not in l]
                    if error_content:
                        for err_line in error_content[-10:]: # 展现最后关键的10行报错
                            print(f"  ▶ {err_line}")
                    else:
                        print("  未捕获到显式文本错误，可能由于强行中断或无文件读取权限。")
                    print("----------------------------------------------------------\n")
                    return False
        except Exception as e:
            print(f"压缩错误 {item_name}: {e}")
            return False
    
    def delete_file(self, file_path):
        """删除单个文件"""
        try:
            os.remove(file_path)
            return True
        except OSError:
            return False

    def delete_item_completely(self, item_path):
        """安全彻底地删除源文件或源文件夹"""
        try:
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
            elif os.path.isfile(item_path):
                os.remove(item_path)
            return True
        except Exception as e:
            print(f"\n❌ 无法删除源项目 {Path(item_path).name}: {e}")
            return False

def find_7zip():
    sevenzip_paths = [
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
        r"D:\Date\7-Zip\7z.exe"
    ]
    for path in sevenzip_paths:
        if os.path.exists(path):
            return path
    return None

def read_file_list(file_list_path):
    if not os.path.exists(file_list_path):
        raise FileNotFoundError(f"文件列表不存在: {file_list_path}")
    with open(file_list_path, 'r', encoding='utf-8') as f:
        files = [strip_quotes(line.strip()) for line in f if line.strip()]  # 去除首尾引号
    valid_files = []
    for file_path in files:
        if os.path.exists(file_path):
            valid_files.append(file_path)
        else:
            print(f"[警告] 路径不存在，已跳过: {file_path}")
    return valid_files

def create_sample_file_list(path):
    sample_content = """# 文件列表示例，每行一个文件或文件夹的完整路径
# 例如：
# D:\\视频\\电影1.mp4
# D:\\文档\\重要资料
"""
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(sample_content)
        print(f"✅ 示例文件列表已创建: {path}")
        print("请用文本编辑器打开并填写实际路径后重试。")
        return True
    except Exception as e:
        print(f"❌ 创建示例文件失败: {e}")
        return False

def get_valid_file_list_interactively(file_list_path):
    """通用引导式文件列表读取与环境校验函数"""
    if not os.path.exists(file_list_path):
        print(f"默认文件列表不存在: {file_list_path}")
        while True:
            print("\n请选择操作：")
            print("1. 输入新的文件列表路径")
            print("2. 创建示例文件列表（在当前目录生成 filelist.txt）")
            print("3. 取消操作")
            choice = input("请输入 (1/2/3): ").strip()
            if choice == '1':
                new_path = strip_quotes(input("请输入文件列表的完整路径: ").strip())  # 去除引号
                if os.path.exists(new_path):
                    file_list_path = new_path
                    break
                else:
                    print("文件不存在，请重新输入或选择其他操作。")
            elif choice == '2':
                sample_path = Path(__file__).parent / "filelist.txt"
                if create_sample_file_list(sample_path):
                    file_list_path = str(sample_path)
                    print(f"已切换到新文件列表: {file_list_path}")
                    input("请编辑文件列表后按回车继续...")
                    if not os.path.exists(file_list_path):
                        print("文件列表仍未创建，操作取消。")
                        return None
                    break
                else:
                    print("创建失败，请重试。")
            elif choice == '3':
                print("操作已取消。")
                return None
            else:
                print("无效输入，请重新选择。")
    try:
        print("正在读取文件列表...")
        res = read_file_list(file_list_path)
        if not res:
            print("\n❌ 错误：关联的文件列表内，没有任何一条路径在电脑中真实存在！")
            input("按回车键返回菜单...")
            return None
        return res
    except Exception as e:
        print(f"读取文件列表出错: {e}")
        input("按回车键返回菜单...")
        return None

def compress_individual_files(compressor, target_format, delete_source=False):
    """[模式1/2] 压缩当前目录下的所有文件（不包含子文件夹）"""
    current_dir = Path(__file__).parent.absolute()
    print("=" * 60)
    print(f"本地单独文件压缩工具 - {target_format.upper()}格式")
    print(f"策略状态: {'【⚠️ 压缩成功后将销毁源文件】' if delete_source else '【安全模式：保留源文件】'}")
    print(f"当前等级: -mx={compressor.compress_level}")
    print("=" * 60)
    
    files = [item for item in current_dir.iterdir() if item.is_file() and item.name != Path(__file__).name]
    if not files:
        print("当前目录没有可压缩的文件！")
        input("按回车键退出...")
        return
    
    # 【A模块明细复活】展现当前本地纯文件列表
    print(f"📋 待单独压缩纯文件明细 ({len(files)}个):")
    total_size = 0
    for file in files:
        file_size = get_item_size(file)
        total_size += file_size
        print(f"  📄 {file.name} ({format_size(file_size)})")
    print(f"总大小: {format_size(total_size)}\n")
    
    confirm = input("确认开始执行？(Y/N): ").strip().upper()
    if confirm != 'Y':
        print("操作已取消。")
        input("按回车键继续...")
        return
    
    success_count = 0
    with tqdm(total=len(files), desc="📦 总体进度", position=0, leave=True, unit="文件") as overall_pbar:
        for file in files:
            target_filename = current_dir / f"{file.stem}.{target_format}"
            if target_filename.exists():
                overall_pbar.update(1)
                continue
            if compressor.compress_with_real_progress(file, target_filename, target_format, file.name, "文件"):
                success_count += 1
                if delete_source:
                    compressor.delete_item_completely(file)
            overall_pbar.update(1)
    
    print(f"\n🎉 处理完毕！成功压缩并归档: {success_count}/{len(files)} 个项目。")
    input("\n按回车键退出...")

def compress_all_items(compressor, target_format, delete_source=False):
    """[模式3/4] 批量压缩当前目录下的所有文件和文件夹"""
    current_dir = Path(__file__).parent.absolute()
    print("=" * 60)
    print(f"本地批量压缩工具 - {target_format.upper()}格式（分离解耦分包）")
    print(f"策略状态: {'【⚠️ 压缩成功后将销毁源文件】' if delete_source else '【安全模式：保留源文件】'}")
    print(f"当前等级: -mx={compressor.compress_level}")
    print("=" * 60)
    
    files = []
    folders = []
    for item in current_dir.iterdir():
        if item.name == Path(__file__).name:
            continue
        if item.is_file():
            files.append(item)
        elif item.is_dir():
            folders.append(item)
    
    total_items = len(files) + len(folders)
    if total_items == 0:
        print("当前目录空空如也！")
        input("按回车键退出...")
        return
    
    # 【A模块明细复活】展现当前本地混编分包明细
    print(f"📋 待分离分包项目明细 ({total_items}个项目):")
    total_size = 0
    if files:
        print("  --- 📄 文件部分 ---")
        for file in files:
            file_size = get_item_size(file)
            total_size += file_size
            print(f"    - {file.name} ({format_size(file_size)})")
    if folders:
        print("  --- 📁 文件夹部分 ---")
        for folder in folders:
            folder_size = get_item_size(folder)
            total_size += folder_size
            print(f"    - {folder.name} ({format_size(folder_size)})")
    print(f"总大小: {format_size(total_size)}\n")
    
    confirm = input("确认开始执行批量任务？(Y/N): ").strip().upper()
    if confirm != 'Y':
        print("操作已取消.")
        input("按回车键继续...")
        return
    
    success_count = 0
    with tqdm(total=total_items, desc="📦 总体进度", position=0, leave=True, unit="项目") as overall_pbar:
        for file in files:
            target_filename = current_dir / f"{file.stem}.{target_format}"
            if target_filename.exists():
                overall_pbar.update(1)
                continue
            if compressor.compress_with_real_progress(file, target_filename, target_format, file.name, "文件"):
                success_count += 1
                if delete_source:
                    compressor.delete_item_completely(file)
            overall_pbar.update(1)
        for folder in folders:
            target_filename = current_dir / f"{folder.name}.{target_format}"
            if target_filename.exists():
                overall_pbar.update(1)
                continue
            if compressor.compress_with_real_progress(folder, target_filename, target_format, folder.name, "文件夹"):
                success_count += 1
                if delete_source:
                    compressor.delete_item_completely(folder)
            overall_pbar.update(1)
            
    print(f"\n🎉 任务结束！成功处理: {success_count}/{total_items} 个项目。")
    input("\n按回车键退出...")

def compress_individual_files_from_list(compressor, target_format, file_list_path, delete_source=False):
    """[模式5/6] 从外部文件列表读取，仅单独压缩列表中的文件（自动跳过文件夹）"""
    file_list = get_valid_file_list_interactively(file_list_path)
    if not file_list:
        return
    
    print("=" * 60)
    print(f"列表文件独立压缩工具 - {target_format.upper()}格式（关联TXT）")
    print(f"策略状态: {'【⚠️ 压缩成功后将销毁源文件】' if delete_source else '【安全模式：保留源文件】'}")
    print(f"当前等级: -mx={compressor.compress_level}")
    print("=" * 60)
    
    files = [Path(item) for item in file_list if os.path.isfile(item)]
    if not files:
        print("文件列表中没有扫描到有效的纯文件路径！")
        input("按回车键退出...")
        return
        
    print(f"📋 待压缩文件明细 ({len(files)}个):")
    total_size = 0
    for file in files:
        file_size = get_item_size(file)
        total_size += file_size
        print(f"  📄 {file.name} ({format_size(file_size)})")
    print(f"总大小: {format_size(total_size)}\n")
        
    confirm = input("确定按照列表处理 these 文件？(Y/N): ").strip().upper()
    if confirm != 'Y':
        print("操作已取消。")
        input("按回车键继续...")
        return
        
    success_count = 0
    with tqdm(total=len(files), desc="📦 总体进度", position=0, leave=True, unit="文件") as overall_pbar:
        for file in files:
            target_filename = file.parent / f"{file.stem}.{target_format}"
            if target_filename.exists():
                overall_pbar.update(1)
                continue
            if compressor.compress_with_real_progress(file, target_filename, target_format, file.name, "文件"):
                success_count += 1
                if delete_source:
                    compressor.delete_item_completely(file)
            overall_pbar.update(1)
            
    print(f"\n🎉 列表文件压缩完毕，成功数: {success_count}/{len(files)}")
    input("\n按回车键退出...")

def compress_all_items_from_list(compressor, target_format, file_list_path, delete_source=False):
    """[模式7/8] 从外部文件列表读取，分别批量压缩列表里的每个文件和文件夹"""
    file_list = get_valid_file_list_interactively(file_list_path)
    if not file_list:
        return
        
    print("=" * 60)
    print(f"列表混编集群压缩工具 - {target_format.upper()}格式（分离打包）")
    print(f"策略状态: {'【⚠️ 压缩成功后将销毁源文件】' if delete_source else '【安全模式：保留源文件】'}")
    print(f"当前等级: -mx={compressor.compress_level}")
    print("=" * 60)
    
    files = [Path(item) for item in file_list if os.path.isfile(item)]
    folders = [Path(item) for item in file_list if os.path.isdir(item)]
    total_items = len(files) + len(folders)
    
    if total_items == 0:
        print("文件列表中没有任何可访问的合法目标路径！")
        input("按回车键退出...")
        return
        
    print(f"📋 待打包分包明细 ({total_items}个项目):")
    total_size = 0
    if files:
        print("  --- 📄 文件部分 ---")
        for file in files:
            file_size = get_item_size(file)
            total_size += file_size
            print(f"    - {file.name} ({format_size(file_size)})")
    if folders:
        print("  --- 📁 文件夹部分 ---")
        for folder in folders:
            folder_size = get_item_size(folder)
            total_size += folder_size
            print(f"    - {folder.name} ({format_size(folder_size)})")
    print(f"总大小: {format_size(total_size)}\n")
        
    confirm = input("确认为整个列表项目开启批量任务？(Y/N): ").strip().upper()
    if confirm != 'Y':
        print("操作已取消。")
        input("按回车键继续...")
        return
        
    success_count = 0
    with tqdm(total=total_items, desc="📦 总体进度", position=0, leave=True, unit="项目") as overall_pbar:
        for file in files:
            target_filename = file.parent / f"{file.stem}.{target_format}"
            if target_filename.exists():
                overall_pbar.update(1)
                continue
            if compressor.compress_with_real_progress(file, target_filename, target_format, file.name, "文件"):
                success_count += 1
                if delete_source:
                    compressor.delete_item_completely(file)
            overall_pbar.update(1)
            
        for folder in folders:
            target_filename = folder.parent / f"{folder.name}.{target_format}"
            if target_filename.exists():
                overall_pbar.update(1)
                continue
            if compressor.compress_with_real_progress(folder, target_filename, target_format, folder.name, "文件夹"):
                success_count += 1
                if delete_source:
                    compressor.delete_item_completely(folder)
            overall_pbar.update(1)
            
    print(f"\n🎉 任务结束！列表批量处理成功数: {success_count}/{total_items}")
    input("\n按回车键退出...")

def triple_compress_files_zip_7z_zip(compressor, file_list_path, delete_source=False):
    """[模式9] 三重压缩：原始 → ZIP → 7Z → ZIP"""
    print("=" * 60)
    print("三重防和谐压缩工具 - 原始 → ZIP → 7Z → ZIP")
    print("显示真实7-Zip进度")
    print(f"当前等级: -mx={compressor.compress_level}")
    print(f"策略状态: {'【⚠️ 压缩成功后将销毁源文件】' if delete_source else '【安全模式：保留源文件】'}")
    print("💡 提示：本模式在运行中会自动创建并销毁中间生成的临时 ZIP/7Z 压缩介质，请放心使用。")
    print("=" * 60)
    
    file_list = get_valid_file_list_interactively(file_list_path)
    if not file_list:
        return
    
    try:
        valid_items = []
        for item_path in file_list:
            if os.path.exists(item_path):
                if os.path.isdir(item_path):
                    valid_items.append((item_path, "文件夹"))
                else:
                    valid_items.append((item_path, "文件"))
        
        print(f"📋 待处理高强度套娃项目明细 ({len(valid_items)}个):")
        total_size = 0
        for item_path, item_type in valid_items:
            item_size = get_item_size(item_path)
            total_size += item_size
            icon = "📁" if item_type == "文件夹" else "📄"
            print(f"  {icon} {Path(item_path).name} ({format_size(item_size)})")
        print(f"总大小: {format_size(total_size)}\n")
        
        # ★ 如果启用了删源，则在此处询问删除时机
        delete_timing = "after_all"  # 默认值
        if delete_source:
            print("\n--- ⏰ 三重压缩删除时机 ---")
            print("1. 第一步压缩完成后【立即删除】原始文件（空间释放早，但中途无法再使用原始文件）")
            print("2. 全部三步压缩完成后【统一删除】原始文件（更安全，全程可保留原始文件）")
            timing = input("请选择删除时机 (1/2): ").strip()
            if timing == "1":
                delete_timing = "immediate"
                print("✅ 已设定：第一步压缩完成后立即删除原始文件。")
            else:
                delete_timing = "after_all"
                print("✅ 已设定：全部三步压缩完成后统一删除原始文件。")
            print()  # 空行
        
        confirm = input("是否开始高强度三重压缩？(Y/N): ").strip().upper()
        if confirm != 'Y':
            print("操作已取消。")
            input("按回车键继续...")
            return
        
        total_items = len(valid_items)
        
        # 第一步：原始 → ZIP
        print("🔄 [第一步] 原始文件/文件夹 → ZIP 格式")
        step1_success = []
        with tqdm(total=total_items, desc="📦 总体进度", position=0, leave=True) as overall_pbar:
            for i, (item_path, item_type) in enumerate(valid_items):
                source_path = Path(item_path)
                if item_type == "文件":
                    zip_path = source_path.parent / (source_path.stem + '.zip')
                else:
                    zip_path = source_path.parent / (source_path.name + '.zip')
                if compressor.compress_with_real_progress(item_path, zip_path, "zip", source_path.name, item_type):
                    step1_success.append((item_path, item_type, zip_path))
                    if delete_source and delete_timing == "immediate":
                        compressor.delete_item_completely(item_path)
                overall_pbar.update(1)
        print()
        
        # 第二步：ZIP → 7Z
        print("🔄 [第二步] ZIP → 7Z 格式 (完成后自动清除临时ZIP)")
        step2_success = []
        step2_items = len(step1_success)
        if step2_items > 0:
            with tqdm(total=step2_items, desc="📦 总体进度", position=0, leave=True) as overall_pbar:
                for i, (item_path, item_type, zip_path) in enumerate(step1_success):
                    if not os.path.exists(zip_path):
                        overall_pbar.update(1)
                        continue
                    source_path = Path(item_path)
                    if item_type == "文件":
                        sevenz_path = source_path.parent / (source_path.stem + '.7z')
                    else:
                        sevenz_path = source_path.parent / (source_path.name + '.7z')
                    if compressor.compress_with_real_progress(zip_path, sevenz_path, "7z", zip_path.name, "ZIP文件"):
                        compressor.delete_file(zip_path)
                        step2_success.append((item_path, item_type, sevenz_path))
                    overall_pbar.update(1)
        print()
        
        # 第三步：7Z → ZIP
        print("🔄 [第三步] 7Z → ZIP 格式 (完成后自动清除临时7Z)")
        step3_success = []
        step3_items = len(step2_success)
        if step3_items > 0:
            with tqdm(total=step3_items, desc="📦 总体进度", position=0, leave=True) as overall_pbar:
                for i, (item_path, item_type, sevenz_path) in enumerate(step2_success):
                    if not os.path.exists(sevenz_path):
                        overall_pbar.update(1)
                        continue
                    source_path = Path(item_path)
                    if item_type == "文件":
                        final_zip_path = source_path.parent / (source_path.stem + '.zip')
                    else:
                        final_zip_path = source_path.parent / (source_path.name + '.zip')
                    if compressor.compress_with_real_progress(sevenz_path, final_zip_path, "zip", sevenz_path.name, "7Z文件"):
                        compressor.delete_file(sevenz_path)
                        step3_success.append((item_path, item_type, final_zip_path))
                    overall_pbar.update(1)
        print()
        
        if delete_source and delete_timing == "after_all":
            print("🔄 正在删除原始源文件...")
            for item_path, item_type, final_path in step3_success:
                if os.path.exists(item_path):
                    compressor.delete_item_completely(item_path)
            print("✅ 原始源文件已全部删除。")
        
        print("=" * 60)
        print(f"🎉 三重防和谐压缩完成！成功处理: {len(step3_success)}/{total_items} 个项目")
        print("=" * 60)
            
    except Exception as e:
        print(f"程序执行出错: {e}")
    input("\n按回车键退出...")
    
def triple_compress_files_7z_zip_7z(compressor, file_list_path, delete_source=False):
    """[模式10] 三重压缩：原始 → 7Z → ZIP → 7Z"""
    print("=" * 60)
    print("三重防和谐压缩工具 - 原始 → 7Z → ZIP → 7Z")
    print("显示真实7-Zip进度")
    print(f"当前等级: -mx={compressor.compress_level}")
    print(f"策略状态: {'【⚠️ 压缩成功后将销毁源文件】' if delete_source else '【安全模式：保留源文件】'}")
    print("💡 提示：本模式在运行中会自动创建并销毁中间生成的临时 ZIP/7Z 压缩介质，请放心使用。")
    print("=" * 60)
    
    file_list = get_valid_file_list_interactively(file_list_path)
    if not file_list:
        return
    
    try:
        valid_items = []
        for item_path in file_list:
            if os.path.exists(item_path):
                if os.path.isdir(item_path):
                    valid_items.append((item_path, "文件夹"))
                else:
                    valid_items.append((item_path, "文件"))
        
        print(f"📋 待处理高强度套娃项目明细 ({len(valid_items)}个):")
        total_size = 0
        for item_path, item_type in valid_items:
            item_size = get_item_size(item_path)
            total_size += item_size
            icon = "📁" if item_type == "文件夹" else "📄"
            print(f"  {icon} {Path(item_path).name} ({format_size(item_size)})")
        print(f"总大小: {format_size(total_size)}\n")
        
        # ★ 如果启用了删源，则在此处询问删除时机
        delete_timing = "after_all"  # 默认值
        if delete_source:
            print("\n--- ⏰ 三重压缩删除时机 ---")
            print("1. 第一步压缩完成后【立即删除】原始文件（空间释放早，但中途无法再使用原始文件）")
            print("2. 全部三步压缩完成后【统一删除】原始文件（更安全，全程可保留原始文件）")
            timing = input("请选择删除时机 (1/2): ").strip()
            if timing == "1":
                delete_timing = "immediate"
                print("✅ 已设定：第一步压缩完成后立即删除原始文件。")
            else:
                delete_timing = "after_all"
                print("✅ 已设定：全部三步压缩完成后统一删除原始文件。")
            print()  # 空行
        
        confirm = input("是否开始高强度三重压缩？(Y/N): ").strip().upper()
        if confirm != 'Y':
            print("操作已取消。")
            input("按回车键继续...")
            return
        
        total_items = len(valid_items)
        
        # 第一步：原始 → 7Z
        print("🔄 [第一步] 原始文件/文件夹 → 7Z 格式")
        step1_success = []
        with tqdm(total=total_items, desc="📦 总体进度", position=0, leave=True) as overall_pbar:
            for i, (item_path, item_type) in enumerate(valid_items):
                source_path = Path(item_path)
                if item_type == "文件":
                    sevenz_path = source_path.parent / (source_path.stem + '.7z')
                else:
                    sevenz_path = source_path.parent / (source_path.name + '.7z')
                if compressor.compress_with_real_progress(item_path, sevenz_path, "7z", source_path.name, item_type):
                    step1_success.append((item_path, item_type, sevenz_path))
                    if delete_source and delete_timing == "immediate":
                        compressor.delete_item_completely(item_path)
                overall_pbar.update(1)
        print()
        
        # 第二步：7Z → ZIP
        print("🔄 [第二步] 7Z → ZIP 格式 (完成后自动清除临时7Z)")
        step2_success = []
        step2_items = len(step1_success)
        if step2_items > 0:
            with tqdm(total=step2_items, desc="📦 总体进度", position=0, leave=True) as overall_pbar:
                for i, (item_path, item_type, sevenz_path) in enumerate(step1_success):
                    if not os.path.exists(sevenz_path):
                        overall_pbar.update(1)
                        continue
                    source_path = Path(item_path)
                    if item_type == "文件":
                        zip_path = source_path.parent / (source_path.stem + '.zip')
                    else:
                        zip_path = source_path.parent / (source_path.name + '.zip')
                    if compressor.compress_with_real_progress(sevenz_path, zip_path, "zip", sevenz_path.name, "7Z文件"):
                        compressor.delete_file(sevenz_path)
                        step2_success.append((item_path, item_type, zip_path))
                    overall_pbar.update(1)
        print()
        
        # 第三步：ZIP → 7Z
        print("🔄 [第三步] ZIP → 7Z 格式 (完成后自动清除临时ZIP)")
        step3_success = []
        step3_items = len(step2_success)
        if step3_items > 0:
            with tqdm(total=step3_items, desc="📦 总体进度", position=0, leave=True) as overall_pbar:
                for i, (item_path, item_type, zip_path) in enumerate(step2_success):
                    if not os.path.exists(zip_path):
                        overall_pbar.update(1)
                        continue
                    source_path = Path(item_path)
                    if item_type == "文件":
                        final_sevenz_path = source_path.parent / (source_path.stem + '.7z')
                    else:
                        final_sevenz_path = source_path.parent / (source_path.name + '.7z')
                    if compressor.compress_with_real_progress(zip_path, final_sevenz_path, "7z", zip_path.name, "ZIP文件"):
                        compressor.delete_file(zip_path)
                        step3_success.append((item_path, item_type, final_sevenz_path))
                    overall_pbar.update(1)
        print()
        
        if delete_source and delete_timing == "after_all":
            print("🔄 正在删除原始源文件...")
            for item_path, item_type, final_path in step3_success:
                if os.path.exists(item_path):
                    compressor.delete_item_completely(item_path)
            print("✅ 原始源文件已全部删除。")
        
        print("=" * 60)
        print(f"🎉 三重防和谐压缩完成！成功处理: {len(step3_success)}/{total_items} 个项目")
        print("=" * 60)
            
    except Exception as e:
        print(f"程序执行出错: {e}")
    input("\n按回车键退出...")
    
def main():
    COMPRESS_LEVEL = 5
    FILE_LIST_PATH = r"D:\视频\filelist.txt"
    
    sevenzip = find_7zip()
    if not sevenzip:
        print("错误: 找不到7-Zip程序!")
        print("请确保已安装7-Zip，或手动修改脚本中的7-Zip路径")
        input("按回车键退出...")
        return
    
    compressor = MultiCompressor(sevenzip, COMPRESS_LEVEL)
    
    while True:
        print("=" * 60)
        print("7-Zip 多功能压缩工具集 - 终极全功能删源+调等版")
        print("显示真实 7-Zip 进度，内置【当前目录】与【文件列表】双模态机制")
        print("=" * 60)
        print("【A. 本地当前目录快速模态】")
        print(" 1. 单独压缩为ZIP格式（当前目录所有文件，不包含子文件夹）")
        print(" 2. 单独压缩为7Z格式（当前目录所有文件，不包含子文件夹）")
        print(" 3. 批量压缩为ZIP格式（当前目录所有文件和文件夹，分别独立分包）")
        print(" 4. 批量压缩为7Z格式（当前目录所有文件和文件夹，分别独立分包）")
        print("【B. 外部TXT文件列表集群模态】")
        print(" 5. 使用文件列表 - 单独压缩为ZIP格式（仅批量单独处理列表内文件）")
        print(" 6. 使用文件列表 - 单独压缩为7Z格式（仅批量单独处理列表内文件）")
        print(" 7. 使用文件列表 - 批量分离压缩为ZIP格式（包含列表文件夹与文件）")
        print(" 8. 使用文件列表 - 批量分离压缩为7Z格式（包含列表文件夹与文件）")
        print("【C. 高强度防爆破三重套娃模态】")
        print(" 9. 三重套娃压缩（原始 → ZIP → 7Z → ZIP，使用文件列表）")
        print(" 10. 三重套娃压缩（原始 → 7Z → ZIP → 7Z，使用文件列表）")
        print("【D. 系统级全局控制参数】")
        print(" 11. 重新指定外部文件列表路径")
        print(f" 12. 修改压缩等级（当前全局设定为: -mx={compressor.compress_level}）")
        print(" 13. 退出程序")
        print()
        
        choice = input("请下达您的压缩指令 (1-13): ").strip()
        
        delete_source = False
        
        # 所有压缩模式（1~10）都支持删除源文件
        if choice in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]:
            print("\n--- ⚡ 盘区空间策略控制 ---")
            print("1. 压缩成功后【保留】源文件 (默认安全模式)")
            print("2. 压缩成功后【全自动删除】源文件 (清空空间模式)")
            del_choice = input("请选择您的源文件策略 (1/2): ").strip()
            
            if del_choice == "2":
                print("\n⚠️  [高危警告] 您已选择压缩后【全自动删除源文件】！")
                confirm_del = input("此操作不仅针对单文件，还包括文件夹。数据不可逆！确认吗？(Y/N): ").strip().upper()
                if confirm_del == 'Y':
                    delete_source = True
                    print("🚀 删源指令已载入，等待7-Zip封包完毕后执行销毁...")
                else:
                    print("已自动降级回【保留源文件】安全模式。")
        
        if choice == "1":
            compress_individual_files(compressor, "zip", delete_source)
        elif choice == "2":
            compress_individual_files(compressor, "7z", delete_source)
        elif choice == "3":
            compress_all_items(compressor, "zip", delete_source)
        elif choice == "4":
            compress_all_items(compressor, "7z", delete_source)
        elif choice == "5":
            compress_individual_files_from_list(compressor, "zip", FILE_LIST_PATH, delete_source)
        elif choice == "6":
            compress_individual_files_from_list(compressor, "7z", FILE_LIST_PATH, delete_source)
        elif choice == "7":
            compress_all_items_from_list(compressor, "zip", FILE_LIST_PATH, delete_source)
        elif choice == "8":
            compress_all_items_from_list(compressor, "7z", FILE_LIST_PATH, delete_source)
        elif choice == "9":
            triple_compress_files_zip_7z_zip(compressor, FILE_LIST_PATH, delete_source)
        elif choice == "10":
            triple_compress_files_7z_zip_7z(compressor, FILE_LIST_PATH, delete_source)
        elif choice == "11":
            print(f"当前默认关联的文件列表路径为: {FILE_LIST_PATH}")
            new_path = strip_quotes(input("请输入全新挂载的 txt 列表文件路径（直接回车则放弃更改）: ").strip())  # 去除引号
            if new_path:
                FILE_LIST_PATH = new_path
                print(f"系统路径全局变量已更新为: {FILE_LIST_PATH}")
            else:
                print("路径未发生变更。")
            input("按回车键继续...")
        elif choice == "12":
            print(f"\n当前全局压缩等级为: -mx={compressor.compress_level}")
            print("指南说明: 0=仅存储不压缩，1=速度最快/体积最大，5=标准平衡(推荐)，9=极限体积/耗时最长")
            new_level_str = input("请输入全新的全局压缩等级 (0-9，直接回车则不修改): ").strip()
            if new_level_str:
                if new_level_str.isdigit() and 0 <= int(new_level_str) <= 9:
                    compressor.compress_level = int(new_level_str)
                    print(f"✅ 全局压缩等级已实时重构为: -mx={compressor.compress_level}")
                else:
                    print("❌ 键入错误！压缩等级必须是 0 互通至 9 之间的整数。")
            else:
                print("策略未发生变更。")
            input("按回车键继续...")
        elif choice == "13":
            print("正在退出压缩工具，感谢您的使用！")
            break
        else:
            print("指令错误，请重新输入 1 至 13 之间的数字！")
            input("按回车键继续...")
            
            
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"程序发生未处理的异常: {e}")
        import traceback
        traceback.print_exc()
        input("按回车键退出...")
