# Deploy Vercel + Supabase + Upstash + Render

Frontend chạy trên Vercel; Supabase cung cấp PostgreSQL; Upstash cung cấp Redis
TCP/TLS; Render chạy API, hai Celery worker, một Beat và ML API nội bộ.
Blueprint dùng image từ workflow Release, cùng một commit SHA cho mọi service.
Không cần chạy Docker Compose trên Render.

## 1. Chuẩn bị Supabase và Upstash

Tạo Supabase project riêng cho JobRadar. Trong Connect, lấy **Session pooler**
port 5432 và đổi scheme thành `postgresql+asyncpg`, query thành `ssl=require`:

```text
postgresql+asyncpg://postgres.PROJECT_REF:PASSWORD@POOLER_HOST:5432/postgres?ssl=require
```

URL-encode password trong DATABASE_URL. DBT_PASSWORD dùng password nguyên bản.
Không dùng transaction pooler 6543 với cấu hình asyncpg hiện tại. Database pool
được giới hạn theo từng process; bắt đầu với DB_POOL_SIZE=2, DB_MAX_OVERFLOW=3
và theo dõi tổng connection khi tăng số worker.

Migration tạo vector, uuid-ossp, pg_trgm, pgcrypto. Nếu extension đã ở schema
`extensions`, kiểm tra search_path của role kết nối có cả `public, extensions`
để tìm được type vector và hàm mã hóa không ghi rõ schema. Dùng role có quyền
migration trong pre-deploy. Trước khi dùng runtime role riêng, cấp quyền bảng,
sequence, schema analytics và kiểm tra policy `app.user_id` của user_profiles.

Ứng dụng giữ cơ chế auth của FastAPI. Tắt Supabase Data API nếu không sử dụng;
không đưa database credential hoặc service-role key vào frontend.

Tạo Upstash Redis, lấy URL TCP/TLS (không phải REST URL):

```text
rediss://default:PASSWORD@HOST:PORT/0?ssl_cert_reqs=required
```

Lấy port đúng từ dashboard. Theo dõi số command và giới hạn connection thực tế;
Celery phát sinh traffic cả khi queue rỗng. Các timeout, broker pool và thời gian
giữ result được cấu hình trong `.env.hosted.example`.

## 2. Chuẩn bị secrets và image

Trong GitHub **repository Variables**, đặt `DEPLOY_TARGET=render` để workflow
Deploy bỏ qua máy self-hosted cũ. CI và Release vẫn hoạt động; thay đổi này không
tự gọi API Render hoặc Vercel.

Chạy workflow Release trên commit chứa các thay đổi hosted. Chỉ dùng image khi
Release hoàn tất thành công, kể cả bước kiểm tra model và security scan.
Hai image cần dùng:

```text
ghcr.io/<owner-chữ-thường>/jobradarvn-backend:<40-character-sha>
ghcr.io/<owner-chữ-thường>/jobradarvn-ml:<40-character-sha>
```

Trong `render.yaml`, thay YOUR_GITHUB_OWNER và RELEASE_SHA bằng owner/SHA thật.
Blueprint không nội suy biến môi trường trong URL image. Với GHCR private,
tạo registry credential chỉ có quyền đọc package trong Render Workspace Settings,
rồi thêm `creds: {fromRegistryCreds: TEN_CREDENTIAL}` dưới từng mục `image`.

Tạo **Environment Group `jobradar-hosted` thủ công trước khi import Blueprint**.
Điền các biến trong `.env.hosted.example`. Không cần upload file .env vào Git.
Tạo bốn secret độc lập cho JWT_SECRET_KEY, ADMIN_API_KEY, CV_ENCRYPTION_KEY và
PROXY_SHARED_SECRET; mỗi secret ít nhất 32 ký tự, ví dụ chạy riêng từng lần:

```bash
openssl rand -hex 32
```

Giữ bản sao CV_ENCRYPTION_KEY ngoài deployment để có thể đọc lại CV từ backup.
CORS_ORIGINS là URL production Vercel/domain thật. Khi thêm domain, cập nhật
allowlist bằng danh sách phân tách dấu phẩy; không dùng wildcard với cookie auth.

## 3. Tạo Render services

Import `render.yaml` qua New Blueprint. File khai báo năm dịch vụ trả phí:

| Service | Vai trò |
| --- | --- |
| jobradar-api | FastAPI public, migration/import trong pre-deploy |
| jobradar-worker | scraping và alerts |
| jobradar-ml-worker | NLP, analytics, task ML; disk /app/artifacts |
| jobradar-beat | scheduler, đúng một instance |
| jobradar-ml-api | private service, model trong image Release |

Chọn region phù hợp với database; Blueprint mặc định Singapore. Các plan trong
file là điểm khởi đầu, đo RAM thực tế khi chạy Chromium và embedding để chỉnh.
Kiểm tra quyền ghi `/app/artifacts` bằng user `jobradar` trong ML worker sau khi
gắn disk. Disk này giữ artifact/MLflow cục bộ, không chia sẻ với ML API.

Ở lần khởi tạo đầu tiên, chỉ cho Beat xử lý lịch sau khi API pre-deploy thành
công; nếu dịch vụ được tạo đồng thời, suspend Beat trong dashboard cho tới lúc
database sẵn sàng. Pre-deploy `scripts/init_hosted_database.sh` chạy migration,
import sáu snapshot idempotent và backfill. Không chạy script này đồng thời từ
worker. Kiểm tra log API: `/health/ready` phải trả 200.

Lấy **internal hostname** của jobradar-ml-api trong Render, đặt riêng trên API:

```text
SALARY_MODEL_URL=http://INTERNAL_ML_HOST:8002
```

Redeploy API. API và ML API phải cùng region/mạng riêng Render. Chạy từ API Shell:

```bash
python -c 'import os, urllib.request; print(urllib.request.urlopen(os.environ["SALARY_MODEL_URL"] + "/health/ready").read().decode())'
```

ML API kiểm tra/cài model khi khởi động; thiếu bundle hoặc sai revision sẽ làm
startup thất bại. `/health/ready` trả 503 nếu model không sẵn sàng. Không đặt
SOURCE_REVISION=local hoặc một SHA khác với SHA được đóng trong image.

Chạy lần đầu trong ML worker Shell:

```bash
dbt build --project-dir analytics --profiles-dir analytics
```

Snapshot lương không xuất hiện như job đang tuyển. Bật nguồn scraper sau khi
kiểm tra policy truy cập hiện tại, rồi trigger thu thập qua admin API. Demo seed
chỉ dành cho môi trường thử, không dùng làm bằng chứng dữ liệu production.

## 4. Deploy Vercel

Import repository, chọn Next.js, Root Directory `web`, Node 24.x, install
`npm ci`, build `npm run build`, output mặc định của Next.js.
Đặt hai biến server-side trước khi deploy:

```text
API_INTERNAL_URL=https://YOUR_API.onrender.com
PROXY_SHARED_SECRET=<giống giá trị trên Render>
```

Không dùng tiền tố NEXT_PUBLIC_ cho secret. Bật system environment variables
để runtime nhận `VERCEL=1`. Redeploy khi đổi API URL hoặc secret. Dùng environment
riêng cho preview nếu không muốn preview truy cập dữ liệu production.

`web/proxy.ts` chuyển `/api`, `/health`, `/version` tới API qua HTTPS, ghi đè
header IP bằng `x-vercel-forwarded-for` do Vercel cung cấp và thêm secret nội bộ.
Server-rendered requests cũng gửi IP theo cùng cách. Cookie đăng nhập tiếp tục
được dùng qua cùng origin của frontend.

Trên Render giữ TRUST_PROXY_HEADERS=false và command `--no-proxy-headers` trong
Blueprint. Khi PROXY_SHARED_SECRET được đặt, API chỉ dùng IP do frontend đã xác
thực gửi; header giả từ request trực tiếp không thay đổi bucket rate limit.
Request anonymous chưa xác thực proxy dùng chung bucket bảo thủ. Đây là cơ chế
xác thực IP cho rate limit, không phải khóa toàn bộ API khỏi truy cập trực tiếp.
Rate limit vẫn theo user ID cho request đã đăng nhập.

Khi không đặt PROXY_SHARED_SECRET, đường chạy Docker/local hiện tại vẫn dùng
rewrite và cấu hình proxy cũ. Không bật hosted secret khi chạy ngoài Vercel;
frontend sẽ fail closed nếu thiếu môi trường/header cần thiết.

## 5. Kiểm tra và cập nhật

Kiểm tra `/health/ready` qua Vercel; đăng ký/đăng nhập, refresh cookie, logout;
job search, analytics, CV upload/đọc lại và ít nhất một task qua Upstash. Gửi
header X-JobRadar-Client-IP giả từ browser phải bị proxy ghi đè. Kiểm tra Redis
và worker logs riêng: API readiness hiện chỉ kiểm tra database.

ENABLE_SALARY_RETRAINING=false tắt lịch retrain định kỳ, các lịch khác giữ nguyên.
Worker không tự cập nhật model đang phục vụ; muốn cập nhật model, chạy Release
mới và đổi toàn bộ URL image sang cùng SHA đã pass. API import/migration cần
hoàn tất trước khi tiếp tục các worker/Beat. Deploy frontend cùng revision.
Render không tự theo dõi tag SHA mới trong GHCR; cập nhật Blueprint để phát hành.

Rollback bằng cách phục hồi URL image của release trước và redeploy. Migration
database không tự rollback; kiểm tra tương thích schema và backup trước khi
phát hành thay đổi phá vỡ tương thích. Backup nằm ở Supabase: cấu hình retention,
export ngoài hệ thống và thử restore; backup service Compose không chạy ở đây.

Tài liệu nền tảng: [Supabase connections](https://supabase.com/docs/guides/database/connecting-to-postgres),
[Upstash Celery](https://upstash.com/docs/redis/integrations/celery),
[Render Blueprint](https://render.com/docs/blueprint-spec),
[Render disks](https://render.com/docs/disks),
[Vercel request headers](https://vercel.com/docs/headers/request-headers),
[Next.js Proxy](https://nextjs.org/docs/app/api-reference/file-conventions/proxy).
