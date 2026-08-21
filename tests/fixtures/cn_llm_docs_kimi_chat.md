> ## Documentation Index
> Fetch the complete documentation index at: https://platform.kimi.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# 模型推理价格说明

> 了解 Kimi 模型推理的 token 计费单位、输入输出计费方式、缓存优惠和各模型价格入口。

## 计费基本概念

### 计费单元

Token：代表常见的字符序列，每个汉字使用的 Token 数目可能是不同的。例如，单个汉字"夔"可能会被分解为若干 Token 的组合，而像"中国"这样短且常见的短语则可能会使用单个 Token。大致来说，对于一段通常的中文文本，1 个 Token 大约相当于 1.5-2 个汉字。具体每次调用实际产生的 Tokens 数量可以通过调用[计算 Token API](/docs/api/estimate) 来获得。

#### 计费逻辑

Chat Completion 接口收费：我们对 Input 和 Output 均实行按量计费。如果您上传并抽取文档内容，并将抽取的文档内容作为 Input 传输给模型，那么文档内容也将按量计费。文件相关接口（文件内容抽取/文件存储）接口**限时免费**，即您只上传并抽取文档，这个API本身不会产生费用。

## 模型定价

请查看各模型的详细定价：

<CardGroup cols={2}>
  <Card title="Kimi K3" icon="rocket" href="/docs/pricing/chat-k3">
    旗舰模型，1M token 上下文
  </Card>

  <Card title="Kimi K2.7 Code" icon="bolt" href="/docs/pricing/chat-k27-code">
    Kimi 的 Coding 模型，多模态模型
  </Card>

  <Card title="Kimi K2.6" icon="star" href="/docs/pricing/chat-k26">
    支持视觉与文本输入
  </Card>

  <Card title="Moonshot V1" icon="moon" href="/docs/pricing/chat-v1">
    经典生成模型系列，预计 8 月 31 日全平台下线
  </Card>
</CardGroup>
