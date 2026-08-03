# SROI規格書
## API Version

* version: v1.1.0
* base URL: `/api/v1`

### 說明
本系統 API 採用版本控制方式管理，目前版本為 `v1.0.0`。  
所有 API 路由皆需加上版本前綴 `/api/v1`，以利未來功能擴充與版本維護。

## auth
### 管理員登入
* http methods: POST
* router: /api/v2/auth`/admin/login`
* request:

|   Name   | Essential |  Type  |               Description                |
|:--------:|:---------:|:------:|:----------------------------------------:|
|  email   |     v     | string |              admin登入帳號               |
| password |     v     | string | admin 登入密碼，後端將進行 hash 比對驗證 |
```json
//request example
{
    "email": "123@gmail.com",
    "password": "Apple6767"
}
```
* response:

|       Name        | Essential |  Type  |   Description   |
|:-----------------:|:---------:|:------:|:---------------:|
|    status code    |     v     | string | API執行狀態代碼 |
|      message      |     v     | string | API執行狀態說明 |
| response_datetime |     v     | string |    回傳時間     |
|       token       |           | string |    登入的JWT    |
```json
// response example
// 成功
{
    "status_code": "00000",
    "message": "success",
    "response_datetime": "2026-03-30 21:35:30",
    "token": "ehflaueyfa73l7ylfp9rgyow3h,ulfeu'0w83",
}

// 失敗
{
    "status_code": "10001",
    "message": "not found",
    "response_datetime": "2026-03-30 21:35:30"
}
```

## form
### 新增表單
* http methods: POST
* router: /api/v1/form`/new`
* header: `Authorization: Bearer <token>`
* response:

|       Name        | Essential |   Description   |
|:-----------------:|:---------:|:---------------:|
|    status code    |     v     | API執行狀態代碼 |
|      message      |     v     | API執行狀態說明 |
| response_datetime |     v     |    回傳時間     |
|      form_id      |           |  新增問卷的id   |
```json
// response example
// 成功
{
    "status_code": "00000",
    "message": "success",
    "response_datetime": "2026-03-30 21:35:30",
    "form_id": "47308576913475"
}

// 失敗
{
    "status_code": "10001",
    "message": "not found",
    "response_datetime": "2026-03-30 21:35:30"
}
```
### 儲存表單
* http methods: POST
* router: /api/v1/form`/save/{FormId}`
* header: `Authorization: Bearer <token>`
* request:

|   Name   | Essential |  Type  |  Description   |
|:--------:|:---------:|:------:|:--------------:|
|  title   |           | string |    問卷標題    |
| content  |           | string |    問卷內文    |
| question |           |  list  | 問卷的所有問題 |
```json
//request example
{
    "title": "",
    "content": "",
    "question": [
        {
            "question_type": "OQ",
            "question_title": "",
            "question_content": "",
            "option": "",
            "dispaly_order": ""
        }
    ]
}
```
* response:

|       Name        | Essential |  Type  |   Description   |
|:-----------------:|:---------:|:------:|:---------------:|
|    status code    |     v     | string | API執行狀態代碼 |
|      message      |     v     | string | API執行狀態說明 |
| response_datetime |     v     | string |    回傳時間     |
```json
// response example
// 成功
{
    "status_code": "00000",
    "message": "success",
    "response_datetime": "2026-03-30 21:35:30",
}

// 失敗
{
    "status_code": "10001",
    "message": "not found",
    "response_datetime": "2026-03-30 21:35:30"
}
```
### 更新表單
* http methods: PUT
* router: /api/v1/form`/update/{FormId}`
* header: `Authorization: Bearer <token>`
* request:

|   Name   | Essential |  Type  |  Description   |
|:--------:|:---------:|:------:|:--------------:|
|  title   |           | string |    問卷標題    |
| content  |           | string |    問卷內文    |
| question |           |  list  | 問卷的所有問題 |
```json
//request example
{
    "title": "",
    "content": "",
    "question": [
        {
            "question_type": "OQ",
            "question_title": "",
            "question_content": "",
            "option": "",
            "dispaly_order": ""
        }
    ]
}
```
* response:

|       Name        | Essential |  Type  |   Description   |
|:-----------------:|:---------:|:------:|:---------------:|
|    status code    |     v     | string | API執行狀態代碼 |
|      message      |     v     | string | API執行狀態說明 |
| response_datetime |     v     | string |    回傳時間     |
```json
// response example
// 成功
{
    "status_code": "00000",
    "message": "success",
    "response_datetime": "2026-03-30 21:35:30",
}

// 失敗
{
    "status_code": "10001",
    "message": "not found",
    "response_datetime": "2026-03-30 21:35:30"
}
```
### 查看表單
* http methods: GET
* router: /api/v1/form`/look/{FormId}`
* header: `Authorization: Bearer <token>`
* response:

|       Name        | Essential |  Type  |   Description   |
|:-----------------:|:---------:|:------:|:---------------:|
|    status code    |     v     | string | API執行狀態代碼 |
|      message      |     v     | string | API執行狀態說明 |
| response_datetime |     v     | string |    回傳時間     |
|       title       |           | string |    問卷標題     |
|      content      |           | string |    問卷內文     |
|     question      |           |  list  | 問卷的所有問題  |
```json
// response example
// 成功
{
    "status_code": "00000",
    "message": "success",
    "response_datetime": "2026-03-30 21:35:30",
    "title": "",
    "content": "",
    "question": [
        {
            "question_type": "OQ",
            "question_title": "",
            "question_content": "",
            "option": "",
            "dispaly_order": ""
        }
    ]
}

// 失敗
{
    "status_code": "10001",
    "message": "not found",
    "response_datetime": "2026-03-30 21:35:30"
}
```


### 發布表單
* http methods: PUT
* router: /api/v1/form`/publish/{form_id}`
* header: `Authorization: Bearer <token>`
* response:

|       Name        | Essential |  Type  |   Description   |
|:-----------------:|:---------:|:------:|:---------------:|
|    status code    |     v     | string | API執行狀態代碼 |
|      message      |     v     | string | API執行狀態說明 |
| response_datetime |     v     | string |    回傳時間     |
|       form_id      |           | int |    已發布的表單 ID     |
|     form_status     |           | string |    表單目前狀態     |
|     published_datetime      |           |  string  | 表單發布時間  |

```json
// response example
// 成功
{
  "status_code": "20000",
  "message": "form published successfully",
  "response_datetime": "2026-07-31 17:30:00",
  "form_id": 1,
  "form_status": "published",
  "published_datetime": "2026-07-31 17:30:00"
}
```
```json
// response example
// 失敗
// 表單不存在
{
  "status_code": "30001",
  "message": "form not found",
  "response_datetime": "2026-07-31 17:30:00"
}

// 表單已經發布
{
  "status_code": "20001",
  "message": "form has already been published",
  "response_datetime": "2026-07-31 17:30:00"
}

// 表單沒有任何題目
{
  "status_code": "20002",
  "message": "form must contain at least one question",
  "response_datetime": "2026-07-31 17:30:00"
}

// 題目資料不完整
{
  "status_code": "20003",
  "message": "question data is incomplete",
  "response_datetime": "2026-07-31 17:30:00"
}

// JWT 無效或已過期
{
  "status_code": "10002",
  "message": "invalid or expired token",
  "response_datetime": "2026-07-31 17:30:00"
}

// 權限不足
{
  "status_code": "10003",
  "message": "permission denied",
  "response_datetime": "2026-07-31 17:30:00"
}
```

### 關閉表單

* http methods: PUT  
* router: /api/v1/form`/close/{form_id}`  
* header: `Authorization: Bearer <token>`
* response:

| Name | Essential | Type | Description |
|------|:---------:|------|-------------|
| status_code | ✓ | string | API 執行狀態代碼 |
| message | ✓ | string | API 執行狀態說明 |
| response_datetime | ✓ | string | 回傳時間 |
| form_id | | int | 已關閉的表單 ID |
| form_status | | string | 表單目前狀態 |
| closed_datetime | | string | 表單關閉時間 |

```json
// response example
// 成功
{
  "status_code": "20000",
  "message": "form closed successfully",
  "response_datetime": "2026-07-31 17:30:00",
  "form_id": 1,
  "form_status": "closed",
  "closed_datetime": "2026-07-31 17:30:00"
}
```

```json
// response example
// 失敗
// 表單不存在
{
  "status_code": "30001",
  "message": "form not found",
  "response_datetime": "2026-07-31 17:30:00"
}
```

```json
// 表單已經關閉
{
  "status_code": "20001",
  "message": "form has already been closed",
  "response_datetime": "2026-07-31 17:30:00"
}
```

```json
// 表單尚未發布
{
  "status_code": "20002",
  "message": "form has not been published",
  "response_datetime": "2026-07-31 17:30:00"
}
```

```json
// JWT 無效或已過期
{
  "status_code": "10002",
  "message": "invalid or expired token",
  "response_datetime": "2026-07-31 17:30:00"
}
```

```json
// 權限不足
{
  "status_code": "10003",
  "message": "permission denied",
  "response_datetime": "2026-07-31 17:30:00"
}
```


<!-- ## 新增表單題目

- http methods: POST
- router: `/api/v1/form/question/new/{form_id}`
- header: `Authorization: Bearer <token>`

### path parameter

| Name | Essential | Type | Description |
| --- | --- | --- | --- |
| form_id | v | string | 欲新增題目的表單 ID |

### request

| Name | Essential | Type | Description |
| --- | --- | --- | --- |
| question_text | v | string | 題目文字 |
| question_type | v | string | 題型 |
| required | v | boolean | 是否為必填題 |
| sort_order | v | integer | 題目顯示順序 |
| metadata |  | object | 題型專屬設定 |
| options | 條件必填 | array  | 單選及複選題的選項 |

### question_type

| Value | Description |
| --- | --- |
| SINGLE_CHOICE | 單選題 |
| MULTIPLE_CHOICE | 複選題 |
| SHORT_ANSWER | 簡答題 |
| DATE | 日期題 |

> `options` 僅適用於 `SINGLE_CHOICE` 與 `MULTIPLE_CHOICE`。  
> `metadata` 依不同題型儲存不同的設定內容。


### 新增單選題

- http methods: POST
- router: `/api/v1/form/{form_id}/question/new`
- header: `Authorization: Bearer <token>`

### path parameter

| Name | Essential | Type | Description |
| --- | --- | --- | --- |
| form_id | v | string | 欲新增題目的表單 ID |

### request

| Name | Essential | Type | Description |
| --- | --- | --- | --- |
| question_type | v | string | 題型，固定為 `single_choice` |
| title | v | string | 題目名稱 |
| description |  | string | 題目說明 |
| required | v | boolean | 是否為必填題 |
| options | v | array | 單選題選項，至少須有兩個 |
| option_id | v | string | 選項 ID |
| option_text | v | string | 選項文字 |
| allow_other | v | boolean | 是否提供「其他」選項 |
| sort | v | integer | 題目顯示順序 |

```json
// request example
{
  "question_type": "single_choice",
  "title": "您的性別為何？",
  "description": "請選擇一個選項",
  "required": true,
  "options": [
    {
      "option_id": "1",
      "option_text": "男性"
    },
    {
      "option_id": "2",
      "option_text": "女性"
    },
    {
      "option_id": "3",
      "option_text": "不願透露"
    }
  ],
  "allow_other": false,
  "sort": 1
```

### 複選題 request

| Name | Essential | Type | Description |
| --- | --- | --- | --- |
| question_text | v | string | 題目文字 |
| question_type | v | string | 固定為 `MULTIPLE_CHOICE` |
| required | v | boolean | 是否必填 |
| sort_order | v | integer | 題目顯示順序 |
| metadata.allow_other | v | boolean | 是否提供「其他」選項 |
| metadata.min_select |  | integer | 最少須選擇幾項 |
| metadata.max_select |  | integer | 最多可選擇幾項 |
| options | v | array | 選項內容，至少須有兩個 |
| options[].label | v | string | 顯示給使用者看的選項文字 |
| options[].value | v | string | 系統儲存的選項值 |
| options[].sort_order | v | integer | 選項顯示順序 |

```json
// request example
{
  "question_text": "您希望租屋處提供哪些設備？",
  "question_type": "MULTIPLE_CHOICE",
  "required": true,
  "sort_order": 2,
  "metadata": {
    "allow_other": true,
    "min_select": 1,
    "max_select": 3
  },
  "options": [
    {
      "label": "冷氣",
      "value": "AIR_CONDITIONER",
      "sort_order": 1
    },
    {
      "label": "洗衣機",
      "value": "WASHING_MACHINE",
      "sort_order": 2
    },
    {
      "label": "冰箱",
      "value": "REFRIGERATOR",
      "sort_order": 3
    },
    {
      "label": "網路",
      "value": "INTERNET",
      "sort_order": 4
    }
  ]
}
```

### 簡答題 request

| Name | Essential | Type | Description |
| --- | --- | --- | --- |
| question_text | v | string | 題目文字 |
| question_type | v | string | 固定為 `SHORT_ANSWER` |
| required | v | boolean | 是否必填 |
| sort_order | v | integer | 題目顯示順序 |
| metadata.placeholder |  | string | 輸入欄位的提示文字 |
| metadata.answer_format | v | string | 可接受的答案格式 |
| metadata.min_length |  | integer | 最少輸入字數 |
| metadata.max_length |  | integer | 最多輸入字數 |

### answer_format

| Value | Description |
| --- | --- |
| TEXT | 一般文字 |
| EMAIL | 電子郵件 |
| NUMBER | 數字 |
| PHONE | 電話號碼 |

```json
// request example
{
  "question_text": "請輸入您的聯絡信箱",
  "question_type": "SHORT_ANSWER",
  "required": true,
  "sort_order": 3,
  "metadata": {
    "placeholder": "example@email.com",
    "answer_format": "EMAIL",
    "min_length": 5,
    "max_length": 100
  }
}
```

### 日期題 request

| Name | Essential | Type | Description |
| --- | --- | --- | --- |
| question_text | v | string | 題目文字 |
| question_type | v | string | 固定為 `DATE` |
| required | v | boolean | 是否必填 |
| sort_order | v | integer | 題目顯示順序 |
| metadata.min_date |  | date | 最早可選日期 |
| metadata.default_date |  | date | 預設日期 |
| metadata.date_format | v | string | 日期格式，固定為 `YYYY-MM-DD` |

```json
// request example
{
  "question_text": "您的預計入住日期為何？",
  "question_type": "DATE",
  "required": true,
  "sort_order": 4,
  "metadata": {
    "min_date": "0001-01-01",
    "default_date": null,
    "date_format": "YYYY-MM-DD"
  }
}
```

### response

| Name | Essential | Type | Description |
| --- | --- | --- | --- |
| status_code | v | string | API 執行狀態代碼 |
| message | v | string | API 執行狀態說明 |
| response_datetime | v | datetime | 回傳時間 |
| form_id |  | string | 表單 ID，成功時回傳 |
| question_id |  | string | 新增題目的 ID，成功時回傳 |
| question_type |  | string | 新增題目的類型，成功時回傳 |

```json
// 成功
{
  "status_code": "00000",
  "message": "success",
  "response_datetime": "2026-07-31 22:30:00",
  "form_id": "47308576913475",
  "question_id": "98310467951234",
  "question_type": "SINGLE_CHOICE"
}
```

```json
// 表單不存在
{
  "status_code": "10001",
  "message": "form not found",
  "response_datetime": "2026-07-31 22:30:00"
}
```

```json
// 請求資料驗證失敗
{
  "status_code": "10002",
  "message": "invalid question data",
  "response_datetime": "2026-07-31 22:30:00"
}
``` -->

## 狀態訊息表
> 說明：
> - 成功統一使用 00000
> - 錯誤依模組分類（Auth / Payment / Query）
> - 採用五碼狀態碼設計，提升可讀性與擴展性

### 🔹 通用狀態碼（00000～09999）

| Status Code | Message           | Description |
| ----------- | ----------------- | ----------- |
| 00000       | success           | 操作成功        |
| 00001       | fail              | 操作失敗        |
| 00002       | invalid_input     | 請求資料格式錯誤    |
| 00003       | unauthorized      | 尚未登入        |
| 00004       | forbidden         | 權限不足        |
| 00005       | not_found         | 資源不存在       |
| 00006       | internal_error    | 系統錯誤        |
| 00007       | too_many_requests | 請求過於頻繁      |


---

### 🔹 認證模組（Auth）（10000～19999）

| Status Code | Message                | Description   |
| ----------- | ---------------------- | ------------- |
| 10001       | user_not_found         | 使用者不存在  |
| 10002       | invalid_password       | 密碼錯誤      |
| 10003       | login_failed           | 登入失敗      |
| 10004       | token_invalid          | token 無效    |
| 10005       | token_expired          | token 過期    |
| 10006       | register_duplicate     | 帳號已存在    |
| 10007       | incorrect_email_format | email格式錯誤 |
| 10008       | permission_denied      | 權限不足      |
| 10009       | incorrect_phone_format | phone格式錯誤 |
| 10010       | password_is_not_strong | 密碼強度不夠  |

---

### 🔹 Form（20000～29999）

| Status Code | Message                     | Description      |
| ----------- | --------------------------- | ---------------- |
| 20001       | form_already_published      | 表單已發布       |
| 20002       | form_has_not_been_published | 表單尚未發布     |
| 20003       | question_data_incomplete    | 題目資料不完整   |
| 20004       | form_has_no_question        | 表單至少需有一題 |
| 20005       | form_already_closed         | 表單已關閉       |
| 20006       | form_save_failed            | 表單儲存失敗     |
| 20007       | form_update_failed          | 表單更新失敗     |
| 20008       | form_publish_failed         | 表單發布失敗     |
| 20009       | form_close_failed           | 表單關閉失敗     |
| 20010       | form_status_invalid         | 表單狀態錯誤     |
| 20011       | question_not_found          | 題目不存在       |
| 20012       | question_type_invalid       | 題型不合法       |
| 20013       | option_data_invalid         | 選項資料錯誤     |

---

### 🔹 查詢模組（30000～39999）

| Status Code | Message            | Description |
| ----------- | ------------------ | ----------- |
| 30001       | form_not_found     | 找不到表單       |
| 30002       | query_no_data      | 查無資料        |
| 30003       | question_not_found | 找不到題目       |
| 30004       | response_not_found | 找不到填答資料     |
| 30005       | query_failed       | 查詢失敗        |

---

### 🔹 Upload（40000～49999）

| Status Code | Message               | Description |
| ----------- | --------------------- | ----------- |
| 40001       | upload_not_an_image   | 上傳檔案不是圖片    |
| 40002       | upload_file_too_large | 檔案超過限制      |
| 40003       | unsupported_file_type | 不支援的檔案格式    |
| 40004       | upload_failed         | 檔案上傳失敗      |
