#!/usr/bin/env python3
# 灵剪 · 配音精确卡点工具（silencedetect）
# ---------------------------------------------------------------
# 画面卡配音的地基:ffmpeg silencedetect 检测配音的停顿点(顿号/冒号/破折号/句读处),
# 每个停顿结束 = 一个语音段(词/词组)的起点。对照台词标点映射,就知道每个关键词的
# 真实时间点 —— 画面事件(章盖/节点点亮/大字揭示)的 start 卡在这些点上,画面就不会
# 比配音快(用户实测反馈的病:画面早于配音)。比 whisper 快(不下模型)、比估算准。
#
# 用法:
#   python3 cadence.py <配音.mp3> [noise_db=-30dB] [min_dur=0.05]
# 输出语音段起点列表;人对照台词标点把关键词对上(见 CADENCE_TABLE.md 的全片映射)。
#
# 卡点规则:画面事件 start ≈ 关键词语音段起点(可提前 0~0.1s 让"砸下"峰值正压在词上);
# 绝不早于词起点(否则画面比配音快)。
import subprocess, sys, re

if len(sys.argv) < 2:
    print("用法: python3 cadence.py <配音.mp3> [noise_db=-30dB] [min_dur=0.05]"); sys.exit(1)
mp3 = sys.argv[1]
noise = sys.argv[2] if len(sys.argv) > 2 else "-30dB"
mindur = sys.argv[3] if len(sys.argv) > 3 else "0.05"

dur = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",mp3],
                     capture_output=True, text=True).stdout.strip()
err = subprocess.run(["ffmpeg","-i",mp3,"-af",f"silencedetect=noise={noise}:d={mindur}","-f","null","-"],
                     capture_output=True, text=True).stderr

segs = [0.0]  # 语音总是从 ~0 开始(开头静音后)
for m in re.finditer(r'silence_end: ([0-9.]+)\s*\|\s*silence_duration: ([0-9.]+)', err):
    segs.append((round(float(m.group(1)), 2), round(float(m.group(2)), 3)))

print(f"# {mp3}  时长 {dur}s  (noise={noise} min_dur={mindur})")
print(f"# 语音段起点(卡点候选) —— 对照台词标点映射关键词:")
print(f"  seg0: 0.0s  (语音开始)")
for i, s in enumerate(segs[1:], 1):
    t, pause = s
    print(f"  seg{i}: {t}s  (前停顿 {pause}s)")
print(f"# 画面事件 start 卡这些点(可 -0.05~0.1s 让砸下峰值压词);绝不早于 → 否则画面比配音快。")
