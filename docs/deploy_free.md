# Deploy miễn phí: Vercel + Supabase + Upstash + Render

Phạm vi đã chọn: web + API demo. Dùng `render.free.yaml`, **không dùng
`render.yaml`** vì file đó tạo năm service trả phí. Chưa chạy Celery worker,
Beat, embedding, ML API hoặc gửi alert tự động trên cloud.

## Tài khoản và cấu hình

1. Đăng nhập Vercel bằng tài khoản cá nhân, dùng gói Hobby cho demo cá nhân.
2. Tạo tài khoản Render và workspace miễn phí; kết nối repository
   `auster-vn/JobRadar` khi được yêu cầu.
3. Tạo organization **Free** và project `jobradar-demo` trên Supabase,
   ưu tiên Singapore. Lưu database password. Trong Connect lấy Session pooler
   port 5432. Tắt Data API nếu chỉ dùng FastAPI để truy cập database.
4. Tạo Redis database `jobradar-demo` trên Upstash, chọn **Free**, không bật
   nâng cấp tự động/pay-as-you-go. Lấy connection string TCP/TLS.

File `.deploy/hosted.env` trên máy đã chứa bốn secret độc lập và được Git bỏ qua.
Điền DATABASE_URL, REDIS_URL và CORS_ORIGINS vào file này bằng editor; không gửi
password/token vào chat. Cú pháp:

```text
DATABASE_URL=postgresql+asyncpg://postgres.PROJECT_REF:URL_ENCODED_PASSWORD@POOLER_HOST:5432/postgres?ssl=require
REDIS_URL=rediss://default:URL_ENCODED_PASSWORD@REDIS_HOST:PORT/0?ssl_cert_reqs=required
CORS_ORIGINS=https://YOUR_PROJECT.vercel.app
```

Các biến DBT_* chưa dùng ở bản demo này. Giữ nguyên PROXY_SHARED_SECRET,
JWT_SECRET_KEY, ADMIN_API_KEY, CV_ENCRYPTION_KEY; không commit file đã điền.

## Render API

Tạo Environment Group `jobradar-hosted`, nhập các biến từ file trên. Import
Blueprint bằng đường dẫn **render.free.yaml**, nhánh `deploy/hosted-platforms`.
Xác nhận service có plan **Free**, không có disk hoặc worker trả phí.
Auto-deploy đang tắt; phát hành thủ công sau khi CI của revision đó pass.

Free service không có pre-deploy hook, nên API chạy `alembic upgrade head` trong
startup rồi mới phục vụ request. Chỉ dùng một instance cho demo. Lần deploy đầu
kiểm tra log migration và endpoint `https://YOUR_API.onrender.com/health/ready`.

Chưa import snapshot trong cold start để tránh kéo dài mỗi lần khởi động.
Để có dữ liệu demo, có thể chạy từ máy local đã có Python dependencies, dùng
đúng DATABASE_URL/REDIS_URL của demo:

```bash
# Load .deploy/hosted.env through a dotenv-aware runner or set the variables
# in your local environment. Do not paste credentials into shell history.
python scripts/seed_demo.py
```

Script seed chỉ dành cho demo. Snapshot lương không phải job đang tuyển. Lần
đầu website chưa có dữ liệu sẽ hiển thị trạng thái rỗng; đó không phải lỗi deploy.
Analytics dbt chưa được tạo nên không coi dashboard analytics là đã hoạt động
đầy đủ. CV embedding/matching nền và delivery alert cần worker ở giai đoạn sau.

## Vercel frontend

Import repository, Root Directory `web`, Next.js, Node 24.x. Dùng Production
Branch `deploy/hosted-platforms` cho project demo. Build `npm run build`,
install `npm ci`, output mặc định. Đặt biến server-side:

```text
API_INTERNAL_URL=https://YOUR_API.onrender.com
PROXY_SHARED_SECRET=<cùng secret trong Render>
```

Bật system environment variables để runtime có VERCEL=1. Không dùng tiền tố
NEXT_PUBLIC_ cho secret. Cập nhật CORS_ORIGINS bên Render bằng URL Vercel thật.
API request đi qua cùng origin của frontend để cookie đăng nhập hoạt động.

## Giới hạn và kiểm tra

Render Free ngủ sau 15 phút không có request; request đầu có thể chậm hoặc phải
thử lại sau khi API thức dậy. Supabase Free có thể pause khi ít hoạt động.
Upstash Free có quota command; không bật Celery chạy liên tục nếu chưa đo quota.
Không cấu hình keep-alive giả để tránh cơ chế ngủ của gói free.

Kiểm tra health qua domain Vercel, đăng ký/đăng nhập/logout, refresh cookie và
job search sau khi seed. Kiểm tra hạn mức trên cả bốn dashboard. Gói free là giới
hạn sử dụng; khi chạm quota chấp nhận gián đoạn thay vì tự nâng cấp có phí.

Nguồn: [Render Free](https://render.com/docs/free),
[Vercel Hobby](https://vercel.com/docs/plans/hobby),
[Supabase pricing](https://supabase.com/pricing),
[Upstash Redis pricing](https://upstash.com/pricing/redis).
