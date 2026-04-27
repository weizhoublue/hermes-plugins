# hook-monitor

日志文件：

```text
~/hermesmonitor/hook.log
```

## 安装

任选一种：

### 方式 1：直接复制目录

```bash
mkdir -p ~/.hermes/plugins
rm -rf ~/.hermes/plugins/hook-monitor
cp -R ./.hermes/plugins/hook-monitor ~/.hermes/plugins/

# 启用
hermes plugins enable hook-monitor
# 或者
# vi ~/.hermes/config.yaml
plugins:
  enabled:
    - hook-monitor

```

### 方式 2：用 `hermes plugins install user/repo`

如果你把这个插件放在独立仓库里，可以直接：

```bash
hermes plugins remove hook-monitor
# github 安装 且自动启用 
hermes plugins install weizhoublue/hermes-plugins  --enable --force
```

## 测试流程

1. 重启 gateway 

```bash

        # 安装新插件后， hermes cli 能立即起效果， 而 飞书等 不能，需要重启下 gateway 进程 
        # 否则 plugin 不能生效

hermes gateway stop
while pgrep -f "hermes.*gateway" > /dev/null; do
    echo "等待旧进程退出..." && sleep 1
done
hermes gateway start


```

2. Hermes CLI 或 channel 进行会话

3. 查看日志

```bash
# 查看 hermes 调用插件的日志
hermes logs --follow

# 查看插件自己的日志
tail -f ~/hermesmonitor/hook.log
```
