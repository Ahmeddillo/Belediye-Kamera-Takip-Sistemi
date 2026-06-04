// Services/ApiService.cs

using System.Net.Http.Json;
using System.Text.Json;
using BelediyeDashboard.Models;

namespace BelediyeDashboard.Services
{
    public interface IApiService
    {
        Task<List<Kamera>> GetKameralarAsync(CancellationToken ct = default);
        Task<SonDakikaVeri?> GetSonDakikaAsync(int kameraId, CancellationToken ct = default);
        Task<SaatlikRapor?> GetSaatlikRaporAsync(int kameraId, string? tarih = null, CancellationToken ct = default);
        Task<GunlukRapor?> GetGunlukRaporAsync(int kameraId, string baslangic, string bitis, CancellationToken ct = default);
        Task<CanliVeri?> GetCanliVeriAsync(int kameraId, int limit = 10, CancellationToken ct = default);

        // HAVA DURUMU
        Task<HavaDurumu?> GetSonHavaDurumuAsync(int kameraId, CancellationToken ct = default);
        Task<HavaDurumuGecmis?> GetHavaDurumuGecmisAsync(int kameraId, string? tarih = null, CancellationToken ct = default);
        Task<List<TumKameralarHavaDurumu>?> GetTumKameralarHavaDurumuAsync(CancellationToken ct = default);
        Task<List<PlakaIslemSonucu>> PlakaIsleAsync(IFormFile dosya);
        Task<AracSayimSonucu?> AracSayAsync(string kaynak, int maxKare = 300, CancellationToken ct = default);

        Task<TrafikYogunlukSonucu?> TrafikYogunlukAsync(string kaynak, CancellationToken ct = default);
    }

    public class ApiService : IApiService
    {
        private readonly HttpClient _httpClient;
        private readonly ILogger<ApiService> _logger;
        private readonly JsonSerializerOptions _jsonOptions;

        public ApiService(HttpClient httpClient, ILogger<ApiService> logger)
        {
            _httpClient = httpClient;
            _logger = logger;
            _jsonOptions = new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            };
        }

        // ── Mevcut metodlar (değişmedi) ──

        public async Task<List<Kamera>> GetKameralarAsync(CancellationToken ct = default)
        {
            try
            {
                var result = await _httpClient.GetFromJsonAsync<List<Kamera>>("/kameralar", _jsonOptions, ct);
                return result ?? new List<Kamera>();
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Kamera listesi alınırken hata oluştu.");
                return new List<Kamera>();
            }
        }

        public async Task<SonDakikaVeri?> GetSonDakikaAsync(int kameraId, CancellationToken ct = default)
        {
            try
            {
                return await _httpClient.GetFromJsonAsync<SonDakikaVeri>($"/son-dakika/{kameraId}", _jsonOptions, ct);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Son dakika verisi alınamadı. KameraId: {KameraId}", kameraId);
                return null;
            }
        }

        public async Task<SaatlikRapor?> GetSaatlikRaporAsync(int kameraId, string? tarih = null, CancellationToken ct = default)
        {
            try
            {
                var query = string.IsNullOrEmpty(tarih) ? "" : $"?tarih={tarih}";
                return await _httpClient.GetFromJsonAsync<SaatlikRapor>($"/saatlik-rapor/{kameraId}{query}", _jsonOptions, ct);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Saatlik rapor alınamadı. KameraId: {KameraId}", kameraId);
                return null;
            }
        }

        public async Task<GunlukRapor?> GetGunlukRaporAsync(int kameraId, string baslangic, string bitis, CancellationToken ct = default)
        {
            try
            {
                var url = $"/gunluk-rapor/{kameraId}?baslangic={baslangic}&bitis={bitis}";
                return await _httpClient.GetFromJsonAsync<GunlukRapor>(url, _jsonOptions, ct);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Günlük rapor alınamadı. KameraId: {KameraId}", kameraId);
                return null;
            }
        }

        public async Task<CanliVeri?> GetCanliVeriAsync(int kameraId, int limit = 10, CancellationToken ct = default)
        {
            try
            {
                return await _httpClient.GetFromJsonAsync<CanliVeri>($"/canli/{kameraId}?limit={limit}", _jsonOptions, ct);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Canlı veri alınamadı. KameraId: {KameraId}", kameraId);
                return null;
            }
        }

        // ── ++ HAVA DURUMU METODLARI ──

        public async Task<HavaDurumu?> GetSonHavaDurumuAsync(int kameraId, CancellationToken ct = default)
        {
            try
            {
                // api.py → GET /hava-durumu/{kamera_id}
                return await _httpClient.GetFromJsonAsync<HavaDurumu>($"/hava-durumu/{kameraId}", _jsonOptions, ct);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Son hava durumu alınamadı. KameraId: {KameraId}", kameraId);
                return null;
            }
        }

        public async Task<HavaDurumuGecmis?> GetHavaDurumuGecmisAsync(int kameraId, string? tarih = null, CancellationToken ct = default)
        {
            try
            {
                // api.py → GET /hava-durumu-gecmis/{kamera_id}?tarih=...
                var query = string.IsNullOrEmpty(tarih) ? "" : $"?tarih={tarih}";
                return await _httpClient.GetFromJsonAsync<HavaDurumuGecmis>(
                    $"/hava-durumu-gecmis/{kameraId}{query}", _jsonOptions, ct);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Hava durumu geçmişi alınamadı. KameraId: {KameraId}", kameraId);
                return null;
            }
        }

        public async Task<List<TumKameralarHavaDurumu>?> GetTumKameralarHavaDurumuAsync(CancellationToken ct = default)
        {
            try
            {
                // api.py → GET /hava-durumu-tum-kameralar
                return await _httpClient.GetFromJsonAsync<List<TumKameralarHavaDurumu>>(
                    "/hava-durumu-tum-kameralar", _jsonOptions, ct);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Tüm kameraların hava durumu alınamadı.");
                return null;
            }
        }

        public async Task<List<PlakaIslemSonucu>> PlakaIsleAsync(IFormFile dosya)
        {
            using var content = new MultipartFormDataContent();
            using var stream = dosya.OpenReadStream();
            using var fileContent = new StreamContent(stream);
            fileContent.Headers.ContentType =
                new System.Net.Http.Headers.MediaTypeHeaderValue(dosya.ContentType);
            content.Add(fileContent, "file", dosya.FileName);

            var response = await _httpClient.PostAsync("plaka/isle", content);

            if (!response.IsSuccessStatusCode)
                return new List<PlakaIslemSonucu>();

            return await response.Content
                .ReadFromJsonAsync<List<PlakaIslemSonucu>>()
                ?? new List<PlakaIslemSonucu>();
        }

        // Araç Sayma Kısmı - ApiService:
        public async Task<AracSayimSonucu?> AracSayAsync(string kaynak, int maxKare = 300, CancellationToken ct = default)
        {
            try
            {
                var url = $"/api/arac-say?kaynak={Uri.EscapeDataString(kaynak)}&max_kare={maxKare}";
                return await _httpClient.GetFromJsonAsync<AracSayimSonucu>(url, _jsonOptions, ct);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Araç sayımı yapılamadı. Kaynak: {Kaynak}", kaynak);
                return null;
            }
        }

        // Trafik Yoğunluk Kısmı - ApiService.cs
        public async Task<TrafikYogunlukSonucu?> TrafikYogunlukAsync(
            string kaynak, CancellationToken ct = default)
        {
            try
            {
                var url = $"/api/trafik-istatistik-stream?kaynak={Uri.EscapeDataString(kaynak)}";
                return await _httpClient.GetFromJsonAsync<TrafikYogunlukSonucu>(url, _jsonOptions, ct);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Trafik yoğunluk analizi yapılamadı. Kaynak: {Kaynak}", kaynak);
                return null;
            }
        }
    }
}
