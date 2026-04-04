# C#（IIS）调用 OCR 微服务示例

本文给出在 IIS 承载的 C# 程序中，调用本项目 OCR 微服务的实用示例。  
接口基址示例：`http://127.0.0.1:8000`

---

## 1. 微服务返回结构（当前版本）

```json
{
  "success": true,
  "traceId": "xxx",
  "elapsedMs": 123,
  "data": {
    "docType": "idcard",
    "fields": {
      "姓名": { "value": "张三", "confidence": 0.88, "source": "anchor:姓名" }
    },
    "text": "..."
  }
}
```

说明：
- 缺失字段也会返回在 `fields` 中，只是 `value=""`
- 业务端建议统一走 `fields["字段名"].value` 映射到实体

---

## 2. 通用 DTO 与调用客户端（同步 + 物理路径上传）

约定：

- 识别请求使用 **`multipart/form-data` + 本地文件路径**（`File.OpenRead`），**不**再走 `imageBase64` JSON。
- 公开方法为**同步**（无 `async`/`await`）；内部可用 `HttpClient.Send`（**.NET 5+**）或 `SendAsync(...).GetAwaiter().GetResult()`（**.NET Framework**）。
- **`OcrHttpClient`**：构造时若传入**系统已注册/单例的 `HttpClient`**（如 DI），则**直接使用**；若未传入，则类内使用**进程级单例** `HttpClient`（懒创建、全进程复用），**无需**在 `Application_Start` 里单独初始化客户端类型本身。

```csharp
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Threading.Tasks;

public class OcrFieldDto
{
    [JsonProperty("value")]
    public JToken Value { get; set; }

    [JsonProperty("confidence")]
    public decimal? Confidence { get; set; }

    [JsonProperty("source")]
    public string Source { get; set; }
}

public class OcrDataDto
{
    [JsonProperty("docType")]
    public string DocType { get; set; }

    [JsonProperty("fields")]
    public Dictionary<string, OcrFieldDto> Fields { get; set; } = new();

    [JsonProperty("text")]
    public string Text { get; set; }
}

public class OcrResponseDto
{
    [JsonProperty("success")]
    public bool Success { get; set; }

    [JsonProperty("traceId")]
    public string TraceId { get; set; }

    [JsonProperty("elapsedMs")]
    public int ElapsedMs { get; set; }

    [JsonProperty("data")]
    public OcrDataDto Data { get; set; }
}

public static class OcrValueReader
{
    public static string GetString(Dictionary<string, OcrFieldDto> fields, string key)
    {
        if (fields == null || !fields.TryGetValue(key, out var f) || f?.Value == null)
            return string.Empty;
        if (f.Value.Type == JTokenType.Null) return string.Empty;
        if (f.Value.Type == JTokenType.Array) return f.Value.ToString(Formatting.None);
        return f.Value.ToString();
    }

    public static DateTime? GetDate(Dictionary<string, OcrFieldDto> fields, string key)
    {
        var s = GetString(fields, key)?.Trim();
        if (string.IsNullOrWhiteSpace(s)) return null;
        if (DateTime.TryParseExact(s, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var dt))
            return dt;
        if (DateTime.TryParse(s, out dt))
            return dt;
        return null;
    }

    public static decimal? GetDecimal(Dictionary<string, OcrFieldDto> fields, string key)
    {
        var s = GetString(fields, key)?.Trim();
        if (decimal.TryParse(s, out var v)) return v;
        return null;
    }

    public static List<string> GetStringList(Dictionary<string, OcrFieldDto> fields, string key)
    {
        if (fields == null || !fields.TryGetValue(key, out var f) || f?.Value == null)
            return new List<string>();
        if (f.Value.Type == JTokenType.Array)
            return f.Value.ToObject<List<string>>() ?? new List<string>();
        var s = f.Value.ToString();
        return string.IsNullOrWhiteSpace(s) ? new List<string>() : new List<string> { s };
    }
}

public class OcrHttpClient
{
    private static readonly object _sharedLock = new object();
    private static HttpClient _sharedProcessClient;

    private readonly HttpClient _http;
    private readonly string _baseUrl;

    /// <param name="baseUrl">例如 http://127.0.0.1:8000</param>
    /// <param name="httpClient">
    /// 若由应用/DI 提供单例 HttpClient，则传入并复用；为 null 时由本类使用进程内单例（懒创建）。
    /// </param>
    public OcrHttpClient(string baseUrl, HttpClient httpClient = null)
    {
        _baseUrl = baseUrl?.TrimEnd('/') ?? throw new ArgumentNullException(nameof(baseUrl));
        if (httpClient != null)
        {
            _http = httpClient;
        }
        else
        {
            lock (_sharedLock)
            {
                if (_sharedProcessClient == null)
                    _sharedProcessClient = CreateDefaultHttpClient();
            }
            _http = _sharedProcessClient;
        }
    }

    private static HttpClient CreateDefaultHttpClient()
    {
        // .NET Core / .NET 5+ 可改用 SocketsHttpHandler 以细调连接池；此处保持默认构造，兼容 .NET Framework IIS。
        return new HttpClient { Timeout = TimeSpan.FromSeconds(60) };
    }

    /// <summary>证件类：docType 为 idcard / vehicle_license / driver_license 等。</summary>
    public OcrResponseDto PostDocumentByFile(string docType, string imageFilePath)
    {
        if (string.IsNullOrWhiteSpace(imageFilePath) || !File.Exists(imageFilePath))
            throw new FileNotFoundException("图片文件不存在", imageFilePath);

        var url = $"{_baseUrl}/v1/ocr/document/{docType}";
        using var form = new MultipartFormDataContent();
        using var fs = File.OpenRead(imageFilePath);
        using var fileContent = new StreamContent(fs);
        fileContent.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
        form.Add(fileContent, "file", Path.GetFileName(imageFilePath));

        using var req = new HttpRequestMessage(HttpMethod.Post, url) { Content = form };
        req.Headers.TryAddWithoutValidation("X-Trace-From", "iis-csharp-client");

        return SendAndDeserialize(req);
    }

    /// <summary>通用 OCR：/v1/ocr/general</summary>
    public OcrResponseDto PostGeneralByFile(string imageFilePath)
    {
        if (string.IsNullOrWhiteSpace(imageFilePath) || !File.Exists(imageFilePath))
            throw new FileNotFoundException("图片文件不存在", imageFilePath);

        var url = $"{_baseUrl}/v1/ocr/general";
        using var form = new MultipartFormDataContent();
        using var fs = File.OpenRead(imageFilePath);
        using var fileContent = new StreamContent(fs);
        fileContent.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
        form.Add(fileContent, "file", Path.GetFileName(imageFilePath));

        using var req = new HttpRequestMessage(HttpMethod.Post, url) { Content = form };
        return SendAndDeserialize(req);
    }

    private OcrResponseDto SendAndDeserialize(HttpRequestMessage req)
    {
        // .NET 5+ 使用同步 Send；若为 .NET Framework 4.x，可改为：
        // using var resp = _http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead).GetAwaiter().GetResult();
        using var resp = _http.Send(req, HttpCompletionOption.ResponseHeadersRead);
        resp.EnsureSuccessStatusCode();
        var json = resp.Content.ReadAsStringAsync().GetAwaiter().GetResult();
        return JsonConvert.DeserializeObject<OcrResponseDto>(json);
    }
}
```

---

## 2.1 可选：`HttpClient` 在 DI 中注册后与 `OcrHttpClient` 组合

若使用 **ASP.NET Core** / **DI**，通常已注册全局 `HttpClient`（或 `IHttpClientFactory` 创建的客户端）。传入后，**所有** `OcrHttpClient` 实例共享该客户端，由容器管理生命周期：

```csharp
// Startup / Program 中已配置单例 HttpClient 时
var apiHttp = serviceProvider.GetRequiredService<HttpClient>();
var ocr = new OcrHttpClient("http://127.0.0.1:8000", apiHttp);
var id = ocr.PostDocumentByFile("idcard", @"G:\data\a.jpg");
```

未传入第二个参数时，`OcrHttpClient` 内部使用**静态懒加载单例** `HttpClient`，同样避免“每请求 new 一个 `HttpClient`”。

---

## 2.2（附录）JSON + `imageBase64` 调用方式

服务端仍支持 `POST` JSON + `imageBase64`（见 `README`）。若必须从内存传图再调用，可自行封装 `StringContent` + `application/json`；**本文主流程已改为物理路径 + multipart，不再展开 base64 示例。**

---

## 3. 对接你的实体（示例映射代码）

> 以下示例使用你给出的实体：`zOcrRes_IdentyCard`、`zOcrRes_VehicleLicense`、`zOcrRes_DrivingLicense`、`zOcrRes_HandWriting`  
> 参数 **`imageFilePath`**：图片在本机上的完整路径，例如 `G:\share\ocr\in\idcard_001.jpg`。

可在业务类中持有**一个** `OcrHttpClient` 字段（构造时传入 `HttpClient` 或省略），识别方法均为**同步**。

### 3.1 身份证识别（`idcard`）

```csharp
public zOcrRes_IdentyCard RecognizeIdCard(string imageFilePath, string logKey)
{
    var client = new OcrHttpClient("http://127.0.0.1:8000"); // 或注入 HttpClient: new OcrHttpClient(baseUrl, _httpClient)
    var resp = client.PostDocumentByFile("idcard", imageFilePath);
    if (resp == null || !resp.Success) throw new Exception($"OCR失败，traceId={resp?.TraceId}");

    var f = resp.Data?.Fields ?? new Dictionary<string, OcrFieldDto>();
    return new zOcrRes_IdentyCard
    {
        PhotoFile = imageFilePath,
        OcrLogKey = logKey,
        身份证号 = OcrValueReader.GetString(f, "身份证号"),
        姓名 = OcrValueReader.GetString(f, "姓名"),
        住址 = OcrValueReader.GetString(f, "住址"),
        出生 = OcrValueReader.GetDate(f, "出生"),
        性别 = OcrValueReader.GetString(f, "性别"),
        民族 = OcrValueReader.GetString(f, "民族")
    };
}
```

### 3.2 行驶证识别（`vehicle_license`）

```csharp
public zOcrRes_VehicleLicense RecognizeVehicleLicense(string imageFilePath, string logKey)
{
    var client = new OcrHttpClient("http://127.0.0.1:8000");
    var resp = client.PostDocumentByFile("vehicle_license", imageFilePath);
    if (resp == null || !resp.Success) throw new Exception($"OCR失败，traceId={resp?.TraceId}");

    var f = resp.Data?.Fields ?? new Dictionary<string, OcrFieldDto>();
    return new zOcrRes_VehicleLicense
    {
        PhotoFile = imageFilePath,
        OcrLogKey = logKey,
        车牌号 = OcrValueReader.GetString(f, "车牌号"),
        车辆识别代号 = OcrValueReader.GetString(f, "车辆识别代号"),
        住址 = OcrValueReader.GetString(f, "住址"),
        发证日期 = OcrValueReader.GetDate(f, "发证日期"),
        发证单位 = OcrValueReader.GetString(f, "发证单位"),
        品牌型号 = OcrValueReader.GetString(f, "品牌型号"),
        车辆类型 = OcrValueReader.GetString(f, "车辆类型"),
        所有人 = OcrValueReader.GetString(f, "所有人"),
        使用性质 = OcrValueReader.GetString(f, "使用性质"),
        发动机号码 = OcrValueReader.GetString(f, "发动机号码"),
        注册日期 = OcrValueReader.GetDate(f, "注册日期")
    };
}
```

### 3.3 驾驶证识别（`driver_license`）

```csharp
public zOcrRes_DrivingLicense RecognizeDrivingLicense(string imageFilePath, string logKey)
{
    var client = new OcrHttpClient("http://127.0.0.1:8000");
    var resp = client.PostDocumentByFile("driver_license", imageFilePath);
    if (resp == null || !resp.Success) throw new Exception($"OCR失败，traceId={resp?.TraceId}");

    var f = resp.Data?.Fields ?? new Dictionary<string, OcrFieldDto>();
    return new zOcrRes_DrivingLicense
    {
        PhotoFile = imageFilePath,
        OcrLogKey = logKey,
        证号 = OcrValueReader.GetString(f, "证号"),
        姓名 = OcrValueReader.GetString(f, "姓名"),
        有效期结束 = OcrValueReader.GetDate(f, "有效期结束"),
        出生日期 = OcrValueReader.GetDate(f, "出生日期"),
        住址 = OcrValueReader.GetString(f, "住址"),
        初次领证日期 = OcrValueReader.GetDate(f, "初次领证日期"),
        国籍 = OcrValueReader.GetString(f, "国籍"),
        准驾车型 = OcrValueReader.GetString(f, "准驾车型"),
        性别 = OcrValueReader.GetString(f, "性别"),
        有效期开始 = OcrValueReader.GetDate(f, "有效期开始"),
        发证单位 = OcrValueReader.GetString(f, "发证单位")
    };
}
```

### 3.4 手写识别（`/v1/ocr/general`）

```csharp
public zOcrRes_HandWriting RecognizeHandWriting(string imageFilePath, string logKey)
{
    var client = new OcrHttpClient("http://127.0.0.1:8000");
    var resp = client.PostGeneralByFile(imageFilePath);
    if (resp == null || !resp.Success) throw new Exception($"OCR失败，traceId={resp?.TraceId}");

    var f = resp.Data?.Fields ?? new Dictionary<string, OcrFieldDto>();
    return new zOcrRes_HandWriting
    {
        PhotoFile = imageFilePath,
        OcrLogKey = logKey,
        全文 = OcrValueReader.GetString(f, "全文"),
        行文本 = OcrValueReader.GetStringList(f, "行文本"),
        置信度 = OcrValueReader.GetDecimal(f, "置信度")
    };
}
```

调用示例：

```csharp
var dto = RecognizeIdCard(@"G:\ocr\in\id.jpg", "OCR-LOG-20260327-0001");
```

---

## 4. IIS 多线程调用建议

- **`HttpClient`**：优先在 **DI** 中注册单例或由 **`IHttpClientFactory`** 创建，并传入 `OcrHttpClient` 第二个参数；未注入时依赖本文内置的**进程级单例**，**不必**在 `Application_Start` 里仅为 OCR 再挂一段初始化。
- **同步调用**：在 ASP.NET **经典**管线中长时间阻塞可能占用线程池，若压测出现排队，可考虑改为异步接口或增大线程池；本文按你方要求保留同步写法。
- 建议业务层增加超时、重试（仅对可重试错误）与日志（记录 `traceId`）。
- OCR 是重计算任务，服务端主要靠 worker 数扩展；客户端不建议无限并发轰炸。

---

## 5. 常见问题

1) 字段为空是不是失败？  
- 不一定。服务会“字段必出”，识别不到时 `value=""`，请按业务规则决定是否人工复核。

2) 日期解析失败怎么办？  
- 先看原始字符串，再做二次兼容解析；示例里已提供 `GetDate` 兜底解析。

3) 必须用物理路径吗？  
- 本文主流程为 **`multipart` 文件上传**（`imageFilePath`）。若只能从内存传图，请改用服务端支持的 JSON + `imageBase64`（见附录 2.2）。

