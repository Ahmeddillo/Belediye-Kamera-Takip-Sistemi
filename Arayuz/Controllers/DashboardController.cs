//DashboardController.cs
using Microsoft.AspNetCore.Mvc;
using OtobusDashboard.Services;
using System.Threading.Tasks;
using System.Linq;
using OtobusDashboard.Models;

namespace OtobusDashboard.Controllers
{
    public class DashboardController : Controller
    {
        private readonly PythonApiService _api;

        public DashboardController(PythonApiService api)
        {
            _api = api;
        }

        // Sayfa ilk açılınca oturumları ve istatistikleri view'e gönderir
        public async Task<IActionResult> Index()
        {
            var oturumlar = await _api.GetOturumlarAsync();
            var kaynaklar = await _api.GetKaynaklarAsync();

            // YENİ: Sürücünün günlük ihlal tablosu
            var surucuIstatistik = await _api.GetSurucuIstatistikAsync();

            ViewBag.Kaynaklar = kaynaklar;
            ViewBag.SurucuIstatistik = surucuIstatistik; // View'a aktar

            return View(oturumlar);
        }

        [HttpPost]
        public async Task<IActionResult> KaynakSec(int kaynakId)
        {
            await _api.KaynakSecAsync(kaynakId);
            return RedirectToAction("Index");
        }

        [HttpGet]
        public async Task<IActionResult> AnlikVeri()
        {
            var veri = await _api.GetAnlikVeriAsync();

            return Json(new
            {
                anlikKisi = veri?.AnlikKisi,
                ortalama = veri?.Ortalama,
                zaman = veri?.Zaman
            });
        }

        [HttpGet]
        public async Task<IActionResult> GecmisVeri(int limit = 50)
        {
            var veri = await _api.GetGecmisAsync(limit);

            return Json(new
            {
                veriler = veri?.Veriler?.Select(v => new {
                    zaman = v.Zaman,
                    anlikKisi = v.AnlikKisi,
                    ortalama = v.Ortalama
                })
            });
        }

        // ==========================================================
        // --- YENİ EKLENEN SÜRÜCÜ JS ENDPOINTİ ---
        // ==========================================================
        [HttpGet]
        public async Task<IActionResult> SurucuCanliVeri()
        {
            var veri = await _api.GetSurucuAnlikVeriAsync();

            return Json(new
            {
                ear = veri?.Ear ?? 0,
                mar = veri?.Mar ?? 0,
                uyariSeviyesi = veri?.UyariSeviyesi ?? "bekleniyor",
                uyariMesaji = veri?.UyariMesaji ?? "",
                yuzTespit = veri?.YuzTespit ?? false
            });
        }


        [HttpGet]
        public async Task<IActionResult> YanginCanliVeri()
        {
            var veri = await _api.GetYanginAnlikVeriAsync();
            return Json(new
            {
                yanginVar = veri?.YanginVar ?? false,
                skor = veri?.Skor ?? 0,
                kutuSayisi = veri?.KutuSayisi ?? 0,
                alarm = veri?.Alarm ?? false,
                zaman = veri?.Zaman ?? ""
            });
        }

        [HttpGet]
        public async Task<IActionResult> YanginGecmis(int limit = 20)
        {
            var veri = await _api.GetYanginGecmisAsync(limit);
            return Json(new
            {
                veriler = veri?.Veriler?.Select(v => new {
                    zaman = v.Zaman,
                    kameraId = v.KameraId,
                    skor = v.Skor,
                    kutuSayisi = v.KutuSayisi,
                    alarm = v.Alarm
                })
            });
        }

        
    }
}
