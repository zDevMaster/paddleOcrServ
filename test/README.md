# test 鐩綍璇存槑

## 鐩綍鐢ㄩ€?

- `data/`锛氭祴璇曞浘鐗囦笌鏁版嵁鐩綍锛堝凡鍦?`test/.gitignore` 涓拷鐣ワ紝涓嶅叆搴擄級
- `test_site.py`锛氭祴璇曠綉绔欏悗绔紙鎵归噺璇嗗埆銆佸垎椤电粨鏋溿€侀潤鎬佸浘鐗囪鍙栵級
- `site/index.html`锛氭祴璇曞叆鍙ｉ〉
- `site/batch_idcard.html`锛氳韩浠借瘉鎵归噺娴嬭瘯椤?
- `site/batch_vehicle_license.html`锛氳椹惰瘉鎵归噺娴嬭瘯椤?
- `site/batch_driver_license.html`锛氶┚椹惰瘉鎵归噺娴嬭瘯椤?
- `start_test_site.bat`锛氭湰鍦板惎鍔ㄦ祴璇曠綉绔欒剼鏈?

## 鍚姩娴嬭瘯缃戠珯

鍏堢‘淇?OCR 寰湇鍔″凡鍚姩锛堥粯璁?`http://127.0.0.1:8000`锛夛紝鐒跺悗鎵ц锛?

```bat
cd /d E:\paddleOcr\test
start_test_site.bat
```

娴忚鍣ㄦ墦寮€锛?

- `http://127.0.0.1:9000`
- 杩涘叆瀵瑰簲鎵归噺椤甸潰锛?
  - 韬唤璇侊細`/batch/idcard`
  - 琛岄┒璇侊細`/batch/vehicle_license`
  - 椹鹃┒璇侊細`/batch/driver_license`

## 鎵归噺娴嬭瘯瑙勫垯

- 姣忔鎵归噺澶勭悊浠呭鐞?**鏈敓鎴愬悓鍚?`.json`** 鐨勫浘鐗?
- 姣忔鎵归噺鏁伴噺鍙€夛紝鑼冨洿 **5-100**
- 璇嗗埆缁撴灉淇濆瓨涓哄悓鍚?`.json`锛堢ず渚嬶細`a.jpg` -> `a.json`锛?
- 涓嬫鐐瑰嚮鈥滄壒閲忔祴璇曗€濅細鑷姩缁х画澶勭悊鍓╀綑鏈瘑鍒枃浠?

## 缁撴灉娴忚

- 灞曠ず璇ョ洰褰曚笅**鍏ㄩ儴鍥剧墖**锛堝寘鍚凡璇嗗埆涓庢湭璇嗗埆锛?
- 宸︿晶鏄剧ず鍘熷鍥剧墖锛屽彸渚ф樉绀哄搴?`.json` 鍐呭
- 閫氳繃鍒嗛〉鍔犺浇渚夸簬浜哄伐鏍稿

## data 鐩綍寤鸿缁撴瀯

- `test/data/idcard`
- `test/data/VehicleLicense`
- `test/data/DrivingLicense`

