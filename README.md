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
```

### 方式 2：用 `hermes plugins install user/repo`

如果你把这个插件放在独立仓库里，可以直接：

```bash
hermes plugins install weizhoublue/hermes-plugins
```

## 启用

```shell
hermes plugins enable hook-monitor

# 或者
# vi ~/.hermes/config.yaml
plugins:
  enabled:
    - hook-monitor
```

## 测试流程

1. 清空旧日志

```bash
rm -f ~/hermesmonitor/hook.log
```

2. Hermes CLI 或 channel 进行会话

3. 查看日志

```bash
# 查看 hermes 调用插件的日志
hermes logs --follow
tai -f ~/hermesmonitor/hook.log

# 查看插件自己的日志
tail -f ~/hermesmonitor/hook.log
```
