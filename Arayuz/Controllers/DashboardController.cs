// Controllers/DashboardController.cs
// Mevcut dosyanın TAM HALİ — hava durumu action'ları eklendi

using Microsoft.AspNetCore.Mvc;
using BelediyeDashboard.Models;
using BelediyeDashboard.Services;
using System.Net.Http;
using System.Text.Json;

namespace BelediyeDashboard.Controllers
{
    public class DashboardController : Controller
    {
        private readonly IApiService _apiService;
        private readonly ILogger<DashboardController> _logger;

        public DashboardController(IApiService apiService, ILogger<DashboardController> logger)
        {
            _apiService = apiService;
            _logger = logger;
        }

        // ── Ana Dashboard (İlk yükleme için SSR) ──
        public async Task<IActionResult> Index()
        {
            var vm = new DashboardViewModel();

            try
            {
                vm.Kameralar = await _apiService.GetKameralarAsync();

                var haftalikBaslangic = DateTime.Now.AddDays(-7).ToString("yyyy-MM-dd");
                var bugun = DateTime.Now.ToString("yyyy-MM-dd");

                var sonDakikaTasks = new Dictionary<int, Task<SonDakikaVeri?>>();
                var saatlikTasks = new Dictionary<int, Task<SaatlikRapor?>>();

                foreach (var kamera in vm.Kameralar)
                {
                    sonDakikaTasks[kamera.Id] = _apiService.GetSonDakikaAsync(kamera.Id);
                    saatlikTasks[kamera.Id] = _apiService.GetSaatlikRaporAsync(kamera.Id);
                }

                await Task.WhenAll(sonDakikaTasks.Values.Concat<Task>(saatlikTasks.Values)); //Burada verilerin yavaşlamasını engellemek için
                // verileri paralel bir şekilde çeker

                foreach (var kamera in vm.Kameralar)
                {
                    vm.SonDakikaVerileri[kamera.Id] = sonDakikaTasks[kamera.Id].Result;
                    vm.SaatlikRaporlar[kamera.Id] = saatlikTasks[kamera.Id].Result;
                }

                if (vm.Kameralar.Any())
                {
                    vm.HaftalikRapor = await _apiService.GetGunlukRaporAsync(
                        vm.Kameralar.First().Id, haftalikBaslangic, bugun);
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Dashboard verileri yüklenirken hata oluştu.");
                TempData["Hata"] = "API bağlantısı kurulamadı. FastAPI servisinin çalıştığından emin olun.";
            }

            return View(vm);
        }

        // ── AJAX: Tek kamera anlık veri ──
        [HttpGet]
        public async Task<IActionResult> CanliVeri(int kameraId)
        {
            var veri = await _apiService.GetCanliVeriAsync(kameraId, limit: 1);

            if (veri?.SonVeriler == null || !veri.SonVeriler.Any())
                return Json(new { kisiSayisi = 0, zaman = DateTime.Now.ToString("HH:mm:ss") });

            var son = veri.SonVeriler.First();
            return Json(new
            {
                kisiSayisi = son.KisiSayisi,
                zaman = son.OlcumZamani.ToString("HH:mm:ss")
            });
        }

        // ── AJAX: Saatlik grafik verisi ──
        [HttpGet]
        public async Task<IActionResult> SaatlikGrafik(int kameraId, string? tarih = null)
        {
            var rapor = await _apiService.GetSaatlikRaporAsync(kameraId, tarih);

            if (rapor == null)
                return Json(new { labels = Array.Empty<string>(), data = Array.Empty<int>() });

            var labels = rapor.SaatlikDetay.Select(s => s.Saat.ToString("HH:00")).ToArray();
            var data = rapor.SaatlikDetay.Select(s => (int)s.OrtalamaKisi).ToArray();
            var pikData = rapor.SaatlikDetay.Select(s => s.PikKisi).ToArray();

            return Json(new { labels, data, pikData, toplamKisi = rapor.ToplamKisi });
        }

        // ── AJAX: Haftalık rapor ──
        [HttpGet]
        public async Task<IActionResult> HaftalikGrafik(int kameraId)
        {
            var baslangic = DateTime.Now.AddDays(-6).ToString("yyyy-MM-dd");
            var bugun = DateTime.Now.ToString("yyyy-MM-dd");

            var rapor = await _apiService.GetGunlukRaporAsync(kameraId, baslangic, bugun);

            if (rapor == null)
                return Json(new { labels = Array.Empty<string>(), data = Array.Empty<int>() });

            var labels = rapor.GunlukDetay.Select(g => g.Gun.ToString("dd MMM")).ToArray();
            var data = rapor.GunlukDetay.Select(g => g.GunlukToplam).ToArray();

            return Json(new { labels, data });
        }

        // ── AJAX: Tüm kameraların anlık durumu ──
        [HttpGet]
        public async Task<IActionResult> TumKameralarDurum()
        {
            try
            {
                var kameralar = await _apiService.GetKameralarAsync();

                var taskList = kameralar.Select(async k =>
                {
                    var canli = await _apiService.GetCanliVeriAsync(k.Id, 1);
                    var sayi = canli?.SonVeriler?.FirstOrDefault()?.KisiSayisi ?? 0;
                    return new { id = k.Id, kisiSayisi = sayi };
                });

                var sonuclar = await Task.WhenAll(taskList);
                return Json(sonuclar);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Tüm kameraların durumu çekilirken hata oluştu.");
                return StatusCode(500, new { mesaj = "Veri çekilemedi" });
            }
        }

        // ── ++ HAVA DURUMU: Detay sayfası (SSR) ──
        [HttpGet]
        public async Task<IActionResult> HavaDurumu()
        {
            var tumKameralar = await _apiService.GetTumKameralarHavaDurumuAsync();
            return View(tumKameralar ?? new List<TumKameralarHavaDurumu>());
        }

        // ── ++ HAVA DURUMU: AJAX — tek kamera son durum ──
        [HttpGet]
        public async Task<IActionResult> HavaDurumuCanli(int kameraId = 1)
        {
            var veri = await _apiService.GetSonHavaDurumuAsync(kameraId);
            return Json(new
            {
                durum = veri?.Durum ?? "Veri yok",
                guvenOrani = veri?.GuvenOrani ?? 0,
                tespitZamani = veri?.TespitZamani ?? ""
            });
        }

        // ── ++ HAVA DURUMU: AJAX — günlük geçmiş ──
        [HttpGet]
        public async Task<IActionResult> HavaDurumuGecmis(int kameraId = 1, string? tarih = null)
        {
            var veri = await _apiService.GetHavaDurumuGecmisAsync(kameraId, tarih);
            return Json(new
            {
                tarih = veri?.Tarih ?? "",
                toplamDegisim = veri?.ToplamDegisim ?? 0,
                durumOzeti = veri?.DurumOzeti ?? new Dictionary<string, int>(),
                gecmis = veri?.Gecmis?.Select(g => new {
                    durum = g.Durum,
                    guvenOrani = g.GuvenOrani,
                    tespitZamani = g.TespitZamani
                }) ?? Enumerable.Empty<object>()
            });
        }

        // ── PLAKA: Upload modal action ──
        [HttpGet]
        public IActionResult Plaka()
        {
            return View();
        }

        [HttpPost]
        public async Task<IActionResult> PlakaIsle(IFormFile dosya)
        {
            if (dosya == null || dosya.Length == 0)
                return Json(new { hata = "Dosya seçilmedi." });

            var izinliUzantilar = new[] { ".jpg", ".jpeg", ".png", ".bmp" };
            var uzanti = Path.GetExtension(dosya.FileName).ToLower();
            if (!izinliUzantilar.Contains(uzanti))
                return Json(new { hata = "Sadece JPG, PNG veya BMP yüklenebilir." });

            try
            {
                // FastAPI'ya dosya gönder
                var sonuclar = await _apiService.PlakaIsleAsync(dosya);

                if (sonuclar == null || sonuclar.Count == 0)
                    return Json(new { hata = "Plaka tespit edilemedi." });

                return Json(sonuclar);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Plaka işleme hatası.");
                return Json(new { hata = "Python servisi yanıt vermedi: " + ex.Message });
            }
        }

        // Araç Sayma kısmı - DashboardController.cs
        [HttpGet]
        public async Task<IActionResult> AracSay(string kaynak, int maxKare = 300)
        {
            if (string.IsNullOrEmpty(kaynak))
                return Json(new { hata = "Kaynak URL'si gereklidir" });

            try
            {
                var sonuc = await _apiService.AracSayAsync(kaynak, maxKare);

                if (sonuc == null)
                    return Json(new { hata = "Python servisi yanıt vermedi." });

                return Json(sonuc);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Araç sayımı hatası");
                return Json(new { hata = $"Hata: {ex.Message}" });
            }
        }

        // Trafik Yoğunluk Kısmı - DashboardController.cs
        [HttpGet]
        public async Task<IActionResult> TrafikYogunluk(string kaynak)
        {
            if (string.IsNullOrEmpty(kaynak))
                return Json(new { hata = "Kaynak URL'si gereklidir" });
            try
            {
                var sonuc = await _apiService.TrafikYogunlukAsync(kaynak);
                if (sonuc == null)
                    return Json(new { hata = "Python servisi yanıt vermedi." });
                return Json(sonuc);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Trafik yoğunluk hatası");
                return Json(new { hata = $"Hata: {ex.Message}" });
            }
        }

    }
}
