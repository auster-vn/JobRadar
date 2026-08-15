import type {Metadata} from "next";

import {AuthPanel} from "@/components/AuthPanel";

export const metadata: Metadata = {title: "Đăng nhập"};

function safeNext(value: string | string[] | undefined) {
  const candidate = Array.isArray(value) ? value[0] : value;
  return candidate?.startsWith("/") && !candidate.startsWith("//") ? candidate : "/profile";
}

export default async function LoginPage({searchParams}: {searchParams: Promise<{next?: string | string[]}>}) {
  const query = await searchParams;
  return <div className="page-stack"><section className="page-heading compact"><div><p className="eyebrow">Tài khoản JobRadar</p><h1>Đăng nhập an toàn</h1><p>Tiếp tục đến hồ sơ, chấm điểm và quy trình ứng tuyển của riêng bạn.</p></div></section><section className="auth-layout"><AuthPanel nextPath={safeNext(query.next)} /></section></div>;
}
