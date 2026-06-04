// Models/HavaDurumuModel.cs
// ApiModels.cs dosyasının yanına ayrı dosya olarak ekle

using System.Text.Json.Serialization;

namespace BelediyeDashboard.Models
{
    public class HavaDurumu
    {
        [JsonPropertyName("kamera_id")]
        public int KameraId { get; set; }

        [JsonPropertyName("durum")]
        public string Durum { get; set; } = string.Empty;

        [JsonPropertyName("guven_orani")]
        public double GuvenOrani { get; set; }

        [JsonPropertyName("tespit_zamani")]
        public string TespitZamani { get; set; } = string.Empty;
    }

    public class HavaDurumuGecmis
    {
        [JsonPropertyName("kamera_id")]
        public int KameraId { get; set; }

        [JsonPropertyName("tarih")]
        public string Tarih { get; set; } = string.Empty;

        [JsonPropertyName("toplam_degisim")]
        public int ToplamDegisim { get; set; }

        [JsonPropertyName("durum_ozeti")]
        public Dictionary<string, int> DurumOzeti { get; set; } = new();

        [JsonPropertyName("gecmis")]
        public List<HavaDurumuKayit> Gecmis { get; set; } = new();
    }

    public class HavaDurumuKayit
    {
        [JsonPropertyName("durum")]
        public string Durum { get; set; } = string.Empty;

        [JsonPropertyName("guven_orani")]
        public double GuvenOrani { get; set; }

        [JsonPropertyName("tespit_zamani")]
        public string TespitZamani { get; set; } = string.Empty;
    }

    public class TumKameralarHavaDurumu
    {
        [JsonPropertyName("kamera_id")]
        public int KameraId { get; set; }

        [JsonPropertyName("kamera_ad")]
        public string KameraAd { get; set; } = string.Empty;

        [JsonPropertyName("konum")]
        public string Konum { get; set; } = string.Empty;

        [JsonPropertyName("durum")]
        public string Durum { get; set; } = string.Empty;

        [JsonPropertyName("guven_orani")]
        public double GuvenOrani { get; set; }

        [JsonPropertyName("tespit_zamani")]
        public string TespitZamani { get; set; } = string.Empty;
    }
}
