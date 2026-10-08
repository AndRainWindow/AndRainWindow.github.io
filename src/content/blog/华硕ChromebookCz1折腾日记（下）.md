---
title: "华硕ChromebookCz1折腾日记（下）"
date: 2026-09-27
updated: "2026-10-08 16:16:25"
topics: "Chromebook"
heroImage: "/images/covers/44caed9d-9c8b-4bb0-bee4-803c26637cc6.webp"
wordCount: 810
readingTime: 3
---

!![Pasted_image_20261008155407.webp](/images/blog/Pasted_image_20261008155407.webp)
#### 启动警告倒计时优化
默认解锁开发者模式后的Bios启动优化倒计时很长，要么手动按按键才能启动，要么等30秒，思路也很简单，把默认启动内部硬盘时间改短就好了。
```Shell
cp spi-original.bin spi-short-delay.bin #备份原始配置

futility gbb -s --flags=0x1 spi-short-delay.bin #修改警告时间

sudo flashrom -p linux_mtd:dev=0 --fmap -i GBB -w spi-short-delay.bin #刷入配置
```

#### 修改默认用户名密码
原始rom设定好了用户名和密码，可能不是我们想要的
```Shell
# su root#进入管理员用户修改

# 1. 如果账户数据库文件被设成 immutable，先解除
sudo chattr -i /etc/passwd /etc/shadow /etc/group /etc/gshadow
# 2. 修改登录用户名
sudo usermod -l wes power
# 3. 修改同名用户组
sudo groupmod -n wes power
# 4. 修改home目录，并把 /home/power 内容一起移动到 /home/wes
sudo usermod -d /home/wes -m wes
# 5. 修改登录界面显示名称
sudo usermod -c "wes" wes
# 6. 确保新用户仍有 sudo 权限
sudo usermod -aG sudo wes
# 7. 检查结果
id wes
getent passwd wes
ls -ld /home/wes
groups wes

sudo hostnamectl set-hostname wes-kukui #主机显示名修改

passwd#修改密码
```

#### 温度墙修改
原生的这个系统温控设置在`/sys/class/thermal/thermal_zone0`中，原始温度墙有三档，分别是68度和80度以及115度，可以改高前面两档，以下是临时方案

```Shell
echo 95000 | sudo tee /sys/class/thermal/thermal_zone0/trip_point_0_temp

echo 103000 | sudo tee /sys/class/thermal/thermal_zone0/trip_point_1_temp
```

持久化方案

```Shell
sudo tee /etc/systemd/system/mt8183-thermal.service >/dev/null <<'EOF'
[Unit]
Description=Set MT8183 thermal trip points
After=local-fs.target
ConditionPathExists=/sys/class/thermal/thermal_zone0/trip_point_0_temp

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'echo 95000 > /sys/class/thermal/thermal_zone0/trip_point_0_temp; echo 103000 > /sys/class/thermal/thermal_zone0/trip_point_1_temp; echo 115000 > /sys/class/thermal/thermal_zone0/trip_point_2_temp'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

# 重新加载 systemd
sudo systemctl daemon-reload

# 设置开机启动，并立即执行一次
sudo systemctl enable --now mt8183-thermal.service
```

#### 设置桌面快捷图标
这个现在桌面还不能在桌面上放图标，其实挺不方便的，以下是把应用图标映射到桌面的方法
```Shell
cp /usr/share/applications/google-chrome.desktop "$(xdg-user-dir DESKTOP)/"
chmod +x "$(xdg-user-dir DESKTOP)/google-chrome.desktop"
gio set "$(xdg-user-dir DESKTOP)/google-chrome.desktop" metadata::trusted true
```

#### 其它
其实这个设备我还折腾了很多，诸如输入法，屏幕键盘，键盘映射，输入法就用的ifcitx的小狼毫开源框架搭配雾凇拼音。然后屏幕键盘和实体键盘映射这个。。。我只能说相当的麻烦，我丢给我的Claude Code做都调试了半天，具体的过程就不写了，总有各种奇奇怪怪的问题，优化到现在之后想着拿来跑Vibe Coding，我也只能说很卡，4G内存真是捉襟见肘，根本不够用的，原装的磁盘还是emmc，划虚拟内存也不是什么可行的方案，总之折腾完这些圆了大学时期的专门GNU/Linux设备梦，然后它暂时就可以去吃灰了，后续有什么新的玩法了可以再说说。
