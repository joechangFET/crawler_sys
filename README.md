# KKTIX Crawler POC

一個以 Playwright 與 Python 打造的非同步網路爬蟲，用於收集 [KKTIX](https://kktix.com) 的活動資訊與座位可用狀態。爬蟲模擬真人瀏覽器操作，自動瀏覽活動列表、擷取票券資訊，並分析座位圖統計數據。

---

## 目錄

- [專案概述](#專案概述)
- [系統架構](#系統架構)
- [專案結構](#專案結構)
- [環境需求](#環境需求)
- [安裝步驟](#安裝步驟)
- [設定說明](#設定說明)
- [執行爬蟲](#執行爬蟲)
- [輸出結果](#輸出結果)
- [活動類型分類](#活動類型分類)
- [部署](#部署)
- [CI/CD 流程](#cicd-流程)

---

## 專案概述

本專案針對 KKTIX 自動化執行以下流程：

1. **Navigate（導航）** — 以隨機延遲模擬真人操作，載入 KKTIX 活動列表頁面。
2. **Login（登入）** — 使用設定的帳號憑證進行驗證，模擬真實的滑鼠與鍵盤輸入行為。
3. **Collect（收集）** — 依設定的活動類別爬取活動網址，並自動翻頁。
4. **Crawl（爬取）** — 針對每個活動擷取後設資料（標題、場次、地點、票券），並進入劃位流程收集各區座位統計。
5. **Persist（儲存）** — 將所有結果匯出至帶有時間戳記的 CSV 檔案。

---

## 系統架構

```
main.py
  └── BrowserManager (core/browser.py)
        └── run_crawler (core/runner.py)
              └── KktixCrawler (sites/kktix/crawler.py)
                    ├── navigate()
                    ├── login()
                    ├── collect()
                    ├── crawl()
                    │     ├── _get_event_title_time_and_location()
                    │     ├── _get_ticket_info()
                    │     ├── _get_seats_map_info()
                    │     │     └── SeatsMap (sites/kktix/map.py)
                    │     └── _click_next_step_and_check_capcha()
                    │           └── Recaptcha (core/recaptcha.py)
                    └── persist()
```

**主要設計決策：**

- `BrowserManager` 管理單一持久性 Chromium 瀏覽器 Context，並以 Semaphore 控制並發數量。持久性 Context 可跨執行重用瀏覽器儲存空間（cookies、localStorage），維持登入狀態。
- `BaseCrawler`（`core/base.py`）定義抽象爬蟲介面。新增爬蟲站點只需在 `sites/<site_name>/crawler.py` 實作對應子類別即可。
- `core/runner.py` 的 `run_crawler` 依站點名稱動態載入爬蟲類別，透過 `asyncio.gather` 支援多站點並行執行。
- 模擬真人行為的邏輯（貝茲曲線滑鼠軌跡、隨機打字延遲、隨機滾動）集中於 `core/human_behavior.py`，供所有爬蟲共用。

---

## 專案結構

```
kktix_crawler_poc/
├── .azure/
│   └── devops-pipelines/
│       ├── fet-cicd-pipeline.yml              # CI/CD 主流程觸發設定
│       ├── pipeline-jobs-deployment.yml       # 正式環境部署工作
│       └── pipeline-jobs-deployment_dev.yml   # 開發環境部署工作
│
├── kktix_crawler_poc/
│   ├── config/
│   │   ├── config_reader.py                   # Singleton YAML/JSON 設定載入器
│   │   ├── enum.py                            # 回應碼與日誌等級列舉
│   │   └── env_loader.py                      # 基於 Pydantic 的環境變數設定
│   │
│   ├── core/
│   │   ├── base.py                            # 抽象 BaseCrawler 類別
│   │   ├── browser.py                         # BrowserManager（Playwright + Stealth）
│   │   ├── human_behavior.py                  # 模擬真人滑鼠、鍵盤、滾動行為
│   │   ├── recaptcha.py                       # reCAPTCHA v2 偵測與 sitekey 擷取
│   │   └── runner.py                          # 動態爬蟲載入與執行器
│   │
│   ├── model/
│   │   ├── enums.py                           # ResultCode 活動分類列舉
│   │   ├── metrics.py                         # StepMetric / FailureMetric TypedDicts
│   │   └── page.py                            # PageResult 資料類別（爬蟲輸出）
│   │
│   ├── sites/
│   │   ├── config/
│   │   │   └── kktix.yaml                     # KKTIX 選擇器與 JS 擷取腳本
│   │   ├── kktix/
│   │   │   ├── __init__.py
│   │   │   ├── crawler.py                     # KktixCrawler 實作
│   │   │   └── map.py                         # SeatsMap — 座位區域互動
│   │   ├── states/
│   │   │   └── kktix.json                     # 持久化瀏覽器儲存狀態
│   │   └── utils.py                           # safe_text、parse_coords、centroid 輔助函式
│   │
│   ├── utils/
│   │   ├── jitter.py                          # 隨機延遲產生器
│   │   ├── logger.py                          # 同時輸出至終端機與檔案的 Logger
│   │   ├── logger_factory.py                  # 建立各站點 Logger 的工廠類別
│   │   └── metrics.py                         # CrawlMetrics 資料類別
│   │
│   ├── logs/                                  # 執行時期日誌輸出（系統與爬蟲）
│   ├── result/                                # CSV 輸出目錄
│   ├── .env                                   # 環境變數（帳號憑證）
│   ├── main.py                                # 非同步程式進入點
│   ├── Dockerfile                             # 容器映像定義
│   ├── k8s-ml.yaml                            # Kubernetes 部署清單
│   └── requirement.txt                        # Python 相依套件
│
└── README.md
```

---

## 環境需求

- Python 3.11 以上
- 已安裝 Google Chrome（爬蟲使用 `channel="chrome"` 啟動持久性 Context）
- 已安裝 Playwright 瀏覽器（詳見[安裝步驟](#安裝步驟)）

---

## 安裝步驟

**1. 複製儲存庫**

```bash
git clone <repository-url>
cd kktix_crawler_poc/kktix_crawler_poc
```

**2. 建立並啟用虛擬環境**

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
.venv\Scripts\activate           # Windows
```

**3. 安裝相依套件**

```bash
pip install -r requirement.txt
```

**4. 安裝 Playwright 瀏覽器**

```bash
playwright install chromium
```

---

## 設定說明

### 環境變數

在 `kktix_crawler_poc/` 目錄下建立 `.env` 檔案：

```env
LOG_LEVEL=INFO
HEADLESS=false
KKTIX_USER=<your_kktix_username>
KKTIX_PASSWORD=<your_kktix_password>
```

這些值由 `config/env_loader.py` 透過 Pydantic `BaseSettings` 於執行時期載入。`LOG_LEVEL`、`KKTIX_USER`、`KKTIX_PASSWORD` 為必填欄位，缺少任一將導致程式無法啟動。`HEADLESS` 預設為 `true`（容器環境），本機開發時設為 `false` 以顯示瀏覽器視窗。

### 站點設定（`sites/config/kktix.yaml`）

| 鍵值 | 說明 |
|---|---|
| `setting.main_url` | KKTIX 活動列表頁面網址 |
| `setting.category` | 要爬取的活動類別清單（例如 `演唱會`） |
| `setting.page` | 翻頁爬取的頁數 |
| `setting.max_retry` | 每個座位區域發生錯誤時的最大重試次數 |
| `contents.disable_keywords` | 用於識別無障礙座位的關鍵字 |
| `selectors.*` | 圖片地圖、氣泡、彈窗、座位表的 CSS 選擇器 |
| `js.extract` | 注入至頁面以擷取圖片地圖座位區域資料的 JavaScript |
| `js.seat_table_stats` | 注入至頁面以統計座位狀態的 JavaScript |

---

## 執行爬蟲

於 `kktix_crawler_poc/` 目錄下執行：

```bash
python main.py
```

爬蟲將依序：
1. 啟動有頭（可見）Chrome 瀏覽器視窗。
2. 導航至 KKTIX，若尚未登入則自動登入，並將瀏覽器儲存狀態儲存至 `sites/states/kktix.json`。
3. 依設定的類別頁面收集活動網址。
4. 針對每個活動網址爬取票券資訊與座位統計。
5. 將結果寫入 `result/kktix_<YYYYMMDD_HHMMSS>.csv`。

日誌輸出位置：
- `logs/system/` — 系統層級啟動日誌
- `logs/crawler/kktix/` — 各活動爬取日誌

---

## 輸出結果

輸出 CSV 中每一列對應一個已爬取的活動，欄位來自 `model/page.py`：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `url` | `str` | 活動頁面網址 |
| `title` | `str` | 活動標題 |
| `schedule` | `str` | 活動日期／時間 |
| `location` | `str` | 活動地點 |
| `event_type` | `str` | 分類結果（詳見下方說明） |
| `tickets` | `list[dict]` | 所有票種資訊，含名稱、座位、價格、售完狀態 |
| `seat_stats` | `list[dict]` | 各區域座位計數（total、able、not_able、already、unknown） |
| `total_seats` | `int` | 座位總數 |
| `available_seats` | `int` | 可用座位總數 |
| `sold_seats` | `int` | 不可用座位總數 |
| `elapsed_time` | `float` | 處理該活動所耗費的秒數 |

---

## 活動類型分類

每個活動依其票券與頁面特徵被賦予一個 `ResultCode`：

| 代碼 | 說明 |
|---|---|
| `Normal` | 一般活動；無座位圖或不適用 |
| `Computer` | 電腦選位活動 — 無法手動選座 |
| `VIP Seat` | VIP 專屬座位 |
| `Disable Seat` | 無障礙／身障座位 |
| `Standing Seat` | 站席票種 |
| `MessageBox` | 進入劃位前出現自訂 CAPTCHA 對話框 |
| `Recaptcha` | 偵測到 Google reCAPTCHA v2 驗證 |
| `Complete` | 成功收集完整座位圖統計資料 |

---

## 部署

### Docker

建置並執行容器映像：

```bash
docker build -t kktix-crawler-poc .
docker run --rm kktix-crawler-poc
```

`Dockerfile` 以 `python:3.11` 為基礎映像，並安裝 `xvfb` 以支援無頭環境中的虛擬顯示。

### Kubernetes

`k8s-ml.yaml` 清單將單一副本部署至 Azure Kubernetes Service（AKS）的 `ml` 命名空間：

```bash
kubectl apply -f k8s-ml.yaml
```

容器映像從 Azure Container Registry 拉取：

```
fetbdcrawacrprod.azurecr.io/kktix_crawler_poc:{version}
```

---

## CI/CD 流程

Azure DevOps 流程定義於 `.azure/devops-pipelines/fet-cicd-pipeline.yml`，自動化完整的建置與部署生命週期：

| 階段 | 觸發條件 | 執行動作 |
|---|---|---|
| `DeployToDev` | 推送至 `dev` 分支 | 建置 Docker 映像 → 推送至 ACR → 部署至 AKS（開發環境） |
| `DeployToProd` | 推送至 `master` 分支 | 建置 Docker 映像 → 推送至 ACR → 部署至 AKS（正式環境） |

每個階段的流程步驟：
1. 簽出原始碼
2. 安裝 Python 3.8 與 `kubectl`
3. 建置帶有建置時間戳記標籤的 Docker 映像
4. 推送映像至 Azure Container Registry
5. 透過 `kubectl apply` 套用 Kubernetes 清單
6. 清理 Agent 工作區
