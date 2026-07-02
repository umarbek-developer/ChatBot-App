Albatta, ushbu qo'llanmani loyihangizning `README.md` fayliga qo'shish uchun qulay va tushunarli formatda tayyorlab berdim.

---

# 🚀 Loyihani ishga tushirish bo'yicha qo'llanma

Ushbu loyihani mahalliy muhitda ishga tushirish uchun quyidagi qadamlarni bajaring.

### 1. Loyihani tayyorlash

Terminalda loyiha papkasiga o'ting va kerakli kutubxonalarni o'rnating:

```bash
# Loyiha papkasiga o'tish
cd src

# Kerakli kutubxonalarni o'rnatish
pip install -r requirements/dev.txt

```

### 2. Ma'lumotlar bazasi va serverni ishga tushirish

Ma'lumotlar bazasini yangilang (migrate) va serverni ishga tushiring:

```bash
# Ma'lumotlar bazasini migratsiya qilish
python manage.py migrate

# Serverni ishga tushirish
python manage.py runserver

```

---

### 🛠 Postman konfiguratsiyasi

API so‘rovlarini test qilish uchun Postman sozlamalarini quyidagicha bajaring:

1. **Postman** ilovasini oching.
2. **Workflows** bo'limiga o'ting va yangi ishchi muhit yarating.
3. Quyidagi fayllarni import qiling:
* `postman-workflows.json`
* `postman-variables.json`



> 💡 **Eslatma:** Batafsil jarayonni tushunish uchun loyiha papkasidagi `postman-workflows-usage.gif` faylini ko‘rib chiqishingiz mumkin.

---

Ushbu qo'llanma bo'yicha yana biror narsani aniqlashtirishim kerakmi?