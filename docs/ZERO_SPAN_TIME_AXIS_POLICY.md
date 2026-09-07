# Zero Span 时间轴覆盖策略

本说明定义 Scope 时域记录与 FSW Zero Span 名义 Sweep Time 之间的覆盖判断。

## 1. 物理覆盖范围

对示波器实际采样时间轴：

```text
t[0], t[1], ..., t[N-1]
```

可直接用于插值而不发生外推的真实覆盖时长定义为：

```text
available_duration = t[N-1] - t[0]
```

不是 `N / Fs`，也不是 `(N-1)/Fs` 的名义推导值优先于真实 CSV 时间戳。

## 2. Sweep Time 超出一个 dt 时的处理

如果：

```text
FSW Sweep Time = available_duration + 1 * dt
```

当前策略为 **拒绝转换**，不把它当作可接受容差。

原因：示波器并没有 `t[N]` 这个真实采样点。若仍生成到该时刻的 FSW 目标轴，`np.interp` 等普通插值会在尾端复制最后一个值，本质上形成静默外推。商业软件不能把这种外推伪装成实测数据。

## 3. 允许的容差

只允许浮点表示/JSON 序列化造成的数值舍入误差：

```text
tolerance = max(abs(scope_duration), abs(sweep_time), 1e-15) * 1e-9
```

该容差远小于一个正常采样间隔，不用于补偿记录长度定义差异。

## 4. 仪表 metadata 约定

如果后续 DSO-X 3034A + FSW 实机验收确认某类 metadata 固定使用 `N/Fs` 作为名义记录长度，而 CSV 最后采样点为 `(N-1)/Fs`，不能在通用插值函数中静默放宽。

正确做法是：

1. 明确记录具体仪表/导出格式的 endpoint convention；
2. 在 metadata 解析层进行显式标准化；
3. 在 conversion metadata 中记录原始值与标准化后的有效值；
4. 增加对应实机 fixture 和回归测试。

在实机约定被确认之前，真实 CSV 的最后采样点始终是覆盖边界的权威来源。

## 5. 当前验收规则

- Sweep Time 小于或等于实际覆盖：允许重采样；
- 仅浮点舍入级超出：允许；
- 超出一个完整 dt：拒绝；
- 明显超出：拒绝；
- 禁止静默尾值延伸。
