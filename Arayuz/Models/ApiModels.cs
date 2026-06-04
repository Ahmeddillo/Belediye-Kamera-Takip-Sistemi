// Models/ApiModels.cs

using System.Text.Json.Serialization;

namespace BelediyeDashboard.Models
{
    public class Kamera
    {
        [JsonPropertyName("id")]
        public int Id { get; set; }

        [JsonPropertyName("ad")]
        public string Ad { get; set; } = string.Empty;

        [JsonPropertyName("konum")]
        public string Konum { get; set; } = string.Empty;

        [JsonPropertyName("kaynak_url")]
        public string KaynakUrl { get; set; } = string.Empty;

        [JsonPropertyName("aktif")]
        public bool Aktif { get; set; }

        [JsonPropertyName("olusturma_tarihi")]
        public DateTime OlusturmaTarihi { get; set; }
    }

    public class SonDakikaVeri
    {
        [JsonPropertyName("kamera")]
        public string Kamera { get; set; } = string.Empty;

        [JsonPropertyName("konum")]
        public string Konum { get; set; } = string.Empty;

        [JsonPropertyName("kaynak")]
        public string Kaynak { get; set; } = string.Empty;

        [JsonPropertyName("veri")]
        public DakikaDetay? Veri { get; set; }
    }

    public class DakikaDetay
    {
        [JsonPropertyName("id")]
        public int Id { get; set; }

        [JsonPropertyName("baslangic_zamani")]
        public DateTime BaslangicZamani { get; set; }

        [JsonPropertyName("bitis_zamani")]
        public DateTime BitisZamani { get; set; }

        [JsonPropertyName("toplam_kisi")]
        public int ToplamKisi { get; set; }

        [JsonPropertyName("ortalama_kisi")]
        public double OrtalamaKisi { get; set; }

        [JsonPropertyName("maksimum_kisi")]
        public int MaksimumKisi { get; set; }

        [JsonPropertyName("minimum_kisi")]
        public int MinimumKisi { get; set; }
    }

    public class SaatlikRapor
    {
        [JsonPropertyName("tarih")]
        public string Tarih { get; set; } = string.Empty;

        [JsonPropertyName("toplam_kisi")]
        public int ToplamKisi { get; set; }

        [JsonPropertyName("saatlik_detay")]
        public List<SaatlikDetay> SaatlikDetay { get; set; } = new();
    }

    public class SaatlikDetay
    {
        [JsonPropertyName("saat")]
        public DateTime Saat { get; set; }

        [JsonPropertyName("dakika_sayisi")]
        public int DakikaSayisi { get; set; }

        [JsonPropertyName("toplam_kisi")]
        public int ToplamKisi { get; set; }

        [JsonPropertyName("ortalama_kisi")]
        public double OrtalamaKisi { get; set; }

        [JsonPropertyName("pik_kisi")]
        public int PikKisi { get; set; }
    }

    public class GunlukRapor
    {
        [JsonPropertyName("baslangic")]
        public string Baslangic { get; set; } = string.Empty;

        [JsonPropertyName("bitis")]
        public string Bitis { get; set; } = string.Empty;

        [JsonPropertyName("gunluk_rapor")]
        public List<GunlukDetay> GunlukDetay { get; set; } = new();
    }

    public class GunlukDetay
    {
        [JsonPropertyName("gun")]
        public DateTime Gun { get; set; }

        [JsonPropertyName("olcum_sayisi")]
        public int OlcumSayisi { get; set; }

        [JsonPropertyName("gunluk_toplam")]
        public int GunlukToplam { get; set; }

        [JsonPropertyName("gunluk_ortalama")]
        public double GunlukOrtalama { get; set; }
    }

    public class CanliVeri
    {
        [JsonPropertyName("kamera_id")]
        public int KameraId { get; set; }

        [JsonPropertyName("son_veriler")]
        public List<AnlikOlcum> SonVeriler { get; set; } = new();
    }

    // ApiModels.cs — JSON alan eşleştirmesi
    public class AnlikOlcum
    {
        [JsonPropertyName("kamera_id")]
        public int KameraId { get; set; }

        [JsonPropertyName("kisi_sayisi")]
        public int KisiSayisi { get; set; }

        [JsonPropertyName("olcum_zamani")]
        public DateTime OlcumZamani { get; set; }
    }

    // Dashboard ViewModel
    public class DashboardViewModel
    {
        public List<Kamera> Kameralar { get; set; } = new();
        public Dictionary<int, SonDakikaVeri?> SonDakikaVerileri { get; set; } = new();
        public Dictionary<int, SaatlikRapor?> SaatlikRaporlar { get; set; } = new();
        public GunlukRapor? HaftalikRapor { get; set; }
        public int ToplamAnlikKisi => SonDakikaVerileri.Values
            .Where(v => v?.Veri != null)
            .Sum(v => v!.Veri!.ToplamKisi);
        public int AktifKameraSayisi => Kameralar.Count(k => k.Aktif);
        public string SonGuncelleme { get; set; } = DateTime.Now.ToString("HH:mm:ss");
    }

    // ── Plaka Tanıma Modelleri ──

    public class PlakaIslemSonucu
    {
        public string Dosya { get; set; } = string.Empty;
        public string HamMetin { get; set; } = string.Empty;
        public string DuzeltilmisMetin { get; set; } = string.Empty;
        public string FormatlıPlaka { get; set; } = string.Empty;
        public bool Gecerli { get; set; }
        public double TespitGuven { get; set; }
        public double OcrGuven { get; set; }
        public string Zaman { get; set; } = string.Empty;
    }

    // ── Araç Sayım Kısmı - ApiModels.cs ──

    public class AracSayimSonucu
    {
        [JsonPropertyName("toplam_arac")]
        public int ToplamArac { get; set; }

        [JsonPropertyName("sinif_sayimlari")]
        public Dictionary<string, int> SinifSayimlari { get; set; } = new();

        [JsonPropertyName("islenen_kare")]
        public int IslenenKare { get; set; }

        [JsonPropertyName("kaynak")]
        public string Kaynak { get; set; } = string.Empty;
    }

    // ── Trafik Yoğunluk Kısmı - ApiModels.cs ──
    public class TrafikYogunlukSonucu
    {
        [JsonPropertyName("ogreniliyor")]
        public bool Ogreniliyor { get; set; }

        [JsonPropertyName("ilerleme")]
        public int Ilerleme { get; set; }

        [JsonPropertyName("kare")]
        public int Kare { get; set; }

        [JsonPropertyName("oran")]
        public double Oran { get; set; }

        [JsonPropertyName("ortalama")]
        public double Ortalama { get; set; }

        [JsonPropertyName("maksimum")]
        public double Maksimum { get; set; }

        [JsonPropertyName("etiket")]
        public string Etiket { get; set; } = string.Empty;

        [JsonPropertyName("gecmis")]
        public List<double> Gecmis { get; set; } = new();
    }
}
