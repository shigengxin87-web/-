#!/usr/bin/env python3
"""
闹钟语音提醒程序
到点后播放中文语音，播报任务名称。
"""

import json
import os
import threading
import time
import uuid
from datetime import datetime

# ─────────────────────────── TTS ───────────────────────────

def _speak(text: str) -> None:
    """使用 pyttsx3 播报中文语音，失败则打印文本。"""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 160)

        # 尝试设置中文语音
        voices = engine.getProperty("voices")
        zh_voice = None
        for v in voices:
            vid = (v.id or "").lower()
            vname = (v.name or "").lower()
            if "zh" in vid or "chinese" in vname or "mandarin" in vname or "cmn" in vid:
                zh_voice = v.id
                break
        if zh_voice:
            engine.setProperty("voice", zh_voice)
        else:
            print("[提示] 未检测到中文语音包，将使用默认语音。")
            print(f"       建议安装：sudo apt-get install espeak-ng-data")

        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except ImportError:
        print(f"\n[语音] {text}")
        print("      (pyttsx3 未安装，请运行: pip install -r requirements.txt)")
    except Exception as e:
        print(f"\n[语音] {text}")
        print(f"      (TTS 播报失败: {e})")


def announce(alarm: dict) -> None:
    """根据闹钟信息生成播报内容并发音。"""
    now = datetime.now()
    hour = now.hour
    minute = now.minute

    if minute == 0:
        time_str = f"现在是{hour}点整"
    else:
        time_str = f"现在是{hour}点{minute}分"

    task = alarm.get("task", "未命名任务")
    text = f"{time_str}，提醒您：{task}"
    print(f"\n🔔 [{alarm['time']}] {task}")
    print(f"   正在播报：{text}")
    # 在独立线程中播报，避免阻塞监控循环
    t = threading.Thread(target=_speak, args=(text,), daemon=True)
    t.start()
    t.join(timeout=30)


# ─────────────────────────── 数据持久化 ───────────────────────────

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alarms.json")


def load_alarms() -> list:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_alarms(alarms: list) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(alarms, f, ensure_ascii=False, indent=2)


# ─────────────────────────── 后台监控 ───────────────────────────

_stop_event = threading.Event()
_triggered_today: set = set()  # 防止同一分钟重复触发


def _monitor_loop() -> None:
    print("\n[监控已启动] 按 Ctrl+C 停止监控并返回主菜单。\n")
    last_date = datetime.now().date()

    while not _stop_event.is_set():
        now = datetime.now()
        current_time = now.strftime("%H:%M")

        # 新的一天，清空已触发记录
        if now.date() != last_date:
            _triggered_today.clear()
            last_date = now.date()

        alarms = load_alarms()
        changed = False

        for alarm in alarms:
            if not alarm.get("enabled", True):
                continue
            if alarm["time"] != current_time:
                continue

            key = f"{alarm['id']}_{current_time}"
            if key in _triggered_today:
                continue

            _triggered_today.add(key)
            announce(alarm)

            # 一次性闹钟触发后禁用
            if not alarm.get("repeat", False):
                alarm["enabled"] = False
                changed = True

        if changed:
            save_alarms(alarms)

        _stop_event.wait(10)  # 每 10 秒检查一次


def start_monitor() -> None:
    _stop_event.clear()
    thread = threading.Thread(target=_monitor_loop, daemon=False)
    thread.start()
    try:
        thread.join()
    except KeyboardInterrupt:
        _stop_event.set()
        thread.join()
        print("\n[监控已停止]")


# ─────────────────────────── CLI ───────────────────────────

def _input_time() -> str:
    """提示用户输入合法的 HH:MM 格式时间。"""
    while True:
        raw = input("请输入闹钟时间（格式 HH:MM，如 09:30）：").strip()
        try:
            datetime.strptime(raw, "%H:%M")
            return raw
        except ValueError:
            print("  格式错误，请重新输入。")


def add_alarm() -> None:
    print("\n── 添加闹钟 ──")
    alarm_time = _input_time()
    task = input("请输入任务名称：").strip()
    if not task:
        print("任务名称不能为空，已取消。")
        return
    repeat_raw = input("每天重复？(y/N)：").strip().lower()
    repeat = repeat_raw == "y"

    alarm = {
        "id": str(uuid.uuid4())[:8],
        "time": alarm_time,
        "task": task,
        "repeat": repeat,
        "enabled": True,
    }
    alarms = load_alarms()
    alarms.append(alarm)
    save_alarms(alarms)
    print(f"✓ 闹钟已添加：{alarm_time} — {task}{'（每天重复）' if repeat else '（仅一次）'}")


def list_alarms() -> None:
    alarms = load_alarms()
    print("\n── 闹钟列表 ──")
    if not alarms:
        print("  （暂无闹钟）")
        return
    for i, a in enumerate(alarms, 1):
        status = "启用" if a.get("enabled", True) else "已触发/禁用"
        repeat = "每天" if a.get("repeat") else "一次"
        print(f"  {i}. [{a['id']}] {a['time']} | {a['task']} | {repeat} | {status}")


def delete_alarm() -> None:
    alarms = load_alarms()
    if not alarms:
        print("  （暂无闹钟可删除）")
        return
    list_alarms()
    raw = input("\n请输入要删除的闹钟编号（或输入 ID 前缀）：").strip()
    new_list = []
    deleted = False
    for i, a in enumerate(alarms, 1):
        if str(i) == raw or a["id"].startswith(raw):
            print(f"✓ 已删除：{a['time']} — {a['task']}")
            deleted = True
        else:
            new_list.append(a)
    if not deleted:
        print("  未找到匹配的闹钟。")
    else:
        save_alarms(new_list)


def toggle_alarm() -> None:
    """启用或禁用某个闹钟。"""
    alarms = load_alarms()
    if not alarms:
        print("  （暂无闹钟）")
        return
    list_alarms()
    raw = input("\n请输入要切换状态的闹钟编号：").strip()
    for i, a in enumerate(alarms, 1):
        if str(i) == raw or a["id"].startswith(raw):
            a["enabled"] = not a.get("enabled", True)
            state = "启用" if a["enabled"] else "禁用"
            print(f"✓ 闹钟 [{a['id']}] 已{state}：{a['time']} — {a['task']}")
            save_alarms(alarms)
            return
    print("  未找到匹配的闹钟。")


def main() -> None:
    print("=" * 40)
    print("      闹钟语音提醒程序")
    print("=" * 40)

    menu = {
        "1": ("添加闹钟", add_alarm),
        "2": ("查看闹钟", list_alarms),
        "3": ("删除闹钟", delete_alarm),
        "4": ("启用/禁用闹钟", toggle_alarm),
        "5": ("启动监控（到点播报语音）", start_monitor),
        "0": ("退出", None),
    }

    while True:
        print("\n请选择操作：")
        for k, (label, _) in menu.items():
            print(f"  {k}. {label}")
        choice = input("输入编号：").strip()

        if choice == "0":
            print("再见！")
            break
        elif choice in menu:
            _, fn = menu[choice]
            if fn:
                fn()
        else:
            print("无效输入，请重试。")


if __name__ == "__main__":
    main()
