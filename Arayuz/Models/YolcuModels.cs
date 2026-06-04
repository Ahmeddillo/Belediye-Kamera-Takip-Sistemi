// YolcuModel.cs
using System;
using System.Collections.Generic;
using System.Text.Json.Serialization;

namespace OtobusDashboard.Models
{
    // --- YOLCU MODELLERİ (Eskiler aynı duruyor) ---
    public class AnlikVeri
    {
        [JsonPropertyName("anlik_kisi")]
        public int AnlikKisi { get; set; }

        [JsonPropertyName("ortalama")]
        public double Ortalama { get; set; }

        [JsonPropertyName("zaman")]
        public string Zaman { get; set; } = "";
    }


    public class Oturum
    {
        [JsonPropertyName("id")]
        public int Id { get; set; }

        [JsonPropertyName("baslangic")]
        public DateTime Baslangic { get; set; }

        [JsonPropertyName("bitis")]
        public DateTime? Bitis { get; set; }

        [JsonPropertyName("video_kaynak")]
        public string VideoKaynak { get; set; } = "";
    }

    public class OturumlarResponse
    {
        [JsonPropertyName("toplam_oturum")]
        public int ToplamOturum { get; set; }

        [JsonPropertyName("oturumlar")]
        public List<Oturum> Oturumlar { get; set; } = new();
    }

    public class GecmisKayit
    {
        [JsonPropertyName("zaman")]
        public DateTime Zaman { get; set; }

        [JsonPropertyName("anlik_kisi")]
        public int AnlikKisi { get; set; }

        [JsonPropertyName("ortalama")]
        public double Ortalama { get; set; }
    }

    public class GecmisResponse
    {
        [JsonPropertyName("kaynak")]
        public string Kaynak { get; set; } = "";

        [JsonPropertyName("oturum_id")]
        public int OturumId { get; set; }

        [JsonPropertyName("kayit_sayisi")]
        public int KayitSayisi { get; set; }

        [JsonPropertyName("veriler")]
        public List<GecmisKayit> Veriler { get; set; } = new();
    }

    public class Kaynak
    {
        [JsonPropertyName("id")]
        public int Id { get; set; }

        [JsonPropertyName("ad")]
        public string Ad { get; set; } = "";

        [JsonPropertyName("kaynak")]
        public string KaynakUrl { get; set; } = "";
    }

    public class KaynakResponse
    {
        [JsonPropertyName("aktif_id")]
        public int AktifId { get; set; }

        [JsonPropertyName("kaynaklar")]
        public List<Kaynak> Kaynaklar { get; set; } = new();
    }

    // ==========================================================
    // --- YENİ EKLENEN SÜRÜCÜ MODELLERİ ---
    // ==========================================================
    public class SurucuAnlikVeri
    {
        [JsonPropertyName("ear")]
        public double Ear { get; set; }

        [JsonPropertyName("mar")]
        public double Mar { get; set; }

        [JsonPropertyName("bas_mesafesi")]
        public double BasMesafesi { get; set; }

        [JsonPropertyName("uyari_seviyesi")]
        public string UyariSeviyesi { get; set; } = "";

        [JsonPropertyName("uyari_mesaji")]
        public string UyariMesaji { get; set; } = "";

        [JsonPropertyName("yuz_tespit")]
        public bool YuzTespit { get; set; }
    }

    public class SurucuIstatistik
    {
        [JsonPropertyName("toplam_uyari")]
        public int ToplamUyari { get; set; }

        [JsonPropertyName("kritik_sayisi")]
        public int KritikSayisi { get; set; }

        [JsonPropertyName("dikkat_sayisi")]
        public int DikkatSayisi { get; set; }
    }


    public class YanginAnlikVeri
    {
        [JsonPropertyName("yangin_var")]
        public bool YanginVar { get; set; }
        [JsonPropertyName("skor")]
        public double Skor { get; set; }
        [JsonPropertyName("kutu_sayisi")]
        public int KutuSayisi { get; set; }
        [JsonPropertyName("alarm")]
        public bool Alarm { get; set; }
        [JsonPropertyName("zaman")]
        public string Zaman { get; set; } = "";
    }

    public class YanginKayit
    {
        [JsonPropertyName("zaman")]
        public string Zaman { get; set; } = "";
        [JsonPropertyName("kamera_id")]
        public string KameraId { get; set; } = "";
        [JsonPropertyName("skor")]
        public double Skor { get; set; }
        [JsonPropertyName("kutu_sayisi")]
        public int KutuSayisi { get; set; }
        [JsonPropertyName("alarm")]
        public bool Alarm { get; set; }
    }

    public class YanginGecmisResponse
    {
        [JsonPropertyName("kayit_sayisi")]
        public int KayitSayisi { get; set; }
        [JsonPropertyName("veriler")]
        public List<YanginKayit> Veriler { get; set; } = new();
    }

}
