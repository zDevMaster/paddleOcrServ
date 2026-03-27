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

## 2. 通用 DTO 与调用客户端

> 建议在 IIS 应用中复用单例 `HttpClient`，避免端口耗尽。

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
using System.Threading;
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
    private static readonly HttpClient _httpClient = BuildHttpClient();
    private readonly string _baseUrl;

    public OcrHttpClient(string baseUrl)
    {
        _baseUrl = baseUrl.TrimEnd('/');
    }

    private static HttpClient BuildHttpClient()
    {
        var handler = new SocketsHttpHandler
        {
            PooledConnectionLifetime = TimeSpan.FromMinutes(10),
            PooledConnectionIdleTimeout = TimeSpan.FromMinutes(2),
            MaxConnectionsPerServer = 200
        };
        return new HttpClient(handler)
        {
            Timeout = TimeSpan.FromSeconds(60)
        };
    }

    public async Task<OcrResponseDto> PostDocumentByFileAsync(string docType, string imagePath, CancellationToken ct = default)
    {
        var url = $"{_baseUrl}/v1/ocr/document/{docType}";

        using var form = new MultipartFormDataContent();
        using var fs = File.OpenRead(imagePath);
        using var fileContent = new StreamContent(fs);
        fileContent.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
        form.Add(fileContent, "file", Path.GetFileName(imagePath));

        using var req = new HttpRequestMessage(HttpMethod.Post, url) { Content = form };
        req.Headers.Add("X-Trace-From", "iis-csharp-client");

        using var resp = await _httpClient.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, ct);
        var json = await resp.Content.ReadAsStringAsync(ct);
        resp.EnsureSuccessStatusCode();
        return JsonConvert.DeserializeObject<OcrResponseDto>(json);
    }

    public async Task<OcrResponseDto> PostGeneralByFileAsync(string imagePath, CancellationToken ct = default)
    {
        var url = $"{_baseUrl}/v1/ocr/general";

        using var form = new MultipartFormDataContent();
        using var fs = File.OpenRead(imagePath);
        using var fileContent = new StreamContent(fs);
        fileContent.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
        form.Add(fileContent, "file", Path.GetFileName(imagePath));

        using var req = new HttpRequestMessage(HttpMethod.Post, url) { Content = form };
        using var resp = await _httpClient.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, ct);
        var json = await resp.Content.ReadAsStringAsync(ct);
        resp.EnsureSuccessStatusCode();
        return JsonConvert.DeserializeObject<OcrResponseDto>(json);
    }

    public async Task<OcrResponseDto> PostDocumentByBase64Async(string docType, string imageBase64, CancellationToken ct = default)
    {
        var url = $"{_baseUrl}/v1/ocr/document/{docType}";
        var body = new
        {
            imageBase64 = imageBase64,
            docType = docType,
            options = new { maxEdge = 1600 }
        };
        var content = new StringContent(JsonConvert.SerializeObject(body), Encoding.UTF8, "application/json");
        using var resp = await _httpClient.PostAsync(url, content, ct);
        var json = await resp.Content.ReadAsStringAsync(ct);
        resp.EnsureSuccessStatusCode();
        return JsonConvert.DeserializeObject<OcrResponseDto>(json);
    }

    public async Task<OcrResponseDto> PostGeneralByBase64Async(string imageBase64, CancellationToken ct = default)
    {
        var url = $"{_baseUrl}/v1/ocr/general";
        var body = new
        {
            imageBase64 = imageBase64,
            options = new { maxEdge = 1600 }
        };
        var content = new StringContent(JsonConvert.SerializeObject(body), Encoding.UTF8, "application/json");
        using var resp = await _httpClient.PostAsync(url, content, ct);
        var json = await resp.Content.ReadAsStringAsync(ct);
        resp.EnsureSuccessStatusCode();
        return JsonConvert.DeserializeObject<OcrResponseDto>(json);
    }
}
```

---

## 2.1 `imageBase64` 工具方法（推荐直接复用）

```csharp
using System;
using System.IO;

public static class OcrImageBase64Helper
{
    // 从图片文件读取并转为纯 base64（不带 data:image 前缀）
    public static string ToBase64FromFile(string imagePath)
    {
        var bytes = File.ReadAllBytes(imagePath);
        return Convert.ToBase64String(bytes);
    }

    // 兼容前端传入 data URL 的情况：data:image/png;base64,xxxx
    public static string NormalizeBase64(string imageBase64OrDataUrl)
    {
        if (string.IsNullOrWhiteSpace(imageBase64OrDataUrl))
            return string.Empty;

        var s = imageBase64OrDataUrl.Trim();
        var marker = "base64,";
        var idx = s.IndexOf(marker, StringComparison.OrdinalIgnoreCase);
        if (idx >= 0)
            return s.Substring(idx + marker.Length);
        return s;
    }
}
```

调用示例（身份证）：

```csharp
var imageBase64 = OcrImageBase64Helper.ToBase64FromFile(@"D:\images\idcard.jpg");
var result = await RecognizeIdCardAsync(imageBase64, @"D:\images\idcard.jpg", "OCR-LOG-20260327-0001");
```

---

## 3. 对接你的实体（示例映射代码）

> 以下示例使用你给出的实体：`zOcrRes_IdentyCard`、`zOcrRes_VehicleLicense`、`zOcrRes_DrivingLicense`、`zOcrRes_HandWriting`

### 3.1 身份证识别（`idcard`）

```csharp
public async Task<zOcrRes_IdentyCard> RecognizeIdCardAsync(string imageBase64, string photoFile, string logKey)
{
    var client = new OcrHttpClient("http://127.0.0.1:8000");
    var resp = await client.PostDocumentByBase64Async("idcard", imageBase64);
    if (resp == null || !resp.Success) throw new Exception($"OCR失败，traceId={resp?.TraceId}");

    var f = resp.Data?.Fields ?? new Dictionary<string, OcrFieldDto>();
    return new zOcrRes_IdentyCard
    {
        PhotoFile = photoFile,
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
public async Task<zOcrRes_VehicleLicense> RecognizeVehicleLicenseAsync(string imageBase64, string photoFile, string logKey)
{
    var client = new OcrHttpClient("http://127.0.0.1:8000");
    var resp = await client.PostDocumentByBase64Async("vehicle_license", imageBase64);
    if (resp == null || !resp.Success) throw new Exception($"OCR失败，traceId={resp?.TraceId}");

    var f = resp.Data?.Fields ?? new Dictionary<string, OcrFieldDto>();
    return new zOcrRes_VehicleLicense
    {
        PhotoFile = photoFile,
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
public async Task<zOcrRes_DrivingLicense> RecognizeDrivingLicenseAsync(string imageBase64, string photoFile, string logKey)
{
    var client = new OcrHttpClient("http://127.0.0.1:8000");
    var resp = await client.PostDocumentByBase64Async("driver_license", imageBase64);
    if (resp == null || !resp.Success) throw new Exception($"OCR失败，traceId={resp?.TraceId}");

    var f = resp.Data?.Fields ?? new Dictionary<string, OcrFieldDto>();
    return new zOcrRes_DrivingLicense
    {
        PhotoFile = photoFile,
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

### 3.4 手写识别（`/v1/ocr/general` 或 `doc_type=handwriting`）

```csharp
public async Task<zOcrRes_HandWriting> RecognizeHandWritingAsync(string imageBase64, string photoFile, string logKey)
{
    var client = new OcrHttpClient("http://127.0.0.1:8000");
    var resp = await client.PostGeneralByBase64Async(imageBase64);
    if (resp == null || !resp.Success) throw new Exception($"OCR失败，traceId={resp?.TraceId}");

    var f = resp.Data?.Fields ?? new Dictionary<string, OcrFieldDto>();
    return new zOcrRes_HandWriting
    {
        PhotoFile = photoFile,
        OcrLogKey = logKey,
        全文 = OcrValueReader.GetString(f, "全文"),
        行文本 = OcrValueReader.GetStringList(f, "行文本"),
        置信度 = OcrValueReader.GetDecimal(f, "置信度")
    };
}
```

---

## 4. IIS 多线程调用建议

- 在 `Application_Start` 或 DI 容器中初始化 `OcrHttpClient`，避免每请求 new `HttpClient`
- 用 `async/await` 全异步，避免线程阻塞
- 建议业务层增加超时、重试（仅对可重试错误）与日志（记录 `traceId`）
- OCR 是重计算任务，服务端主要靠 worker 数扩展；客户端不建议无限并发轰炸

---

## 5. 常见问题

1) 字段为空是不是失败？  
- 不一定。服务会“字段必出”，识别不到时 `value=""`，请按业务规则决定是否人工复核。

2) 日期解析失败怎么办？  
- 先看原始字符串，再做二次兼容解析；示例里已提供 `GetDate` 兜底解析。

3) 需要传 base64 吗？  
- 本文示例统一使用 base64；如果你更关注性能，也可以改用文件上传接口。

