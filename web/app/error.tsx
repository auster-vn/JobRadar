"use client";

import {CircleAlert} from "lucide-react";
import {useEffect} from "react";

export default function ErrorPage({error, reset}: {error: Error & {digest?: string}; reset: () => void}) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return <section className="panel workspace-state" role="alert"><CircleAlert size={28} /><h1>Không thể tải dữ liệu</h1><span>Dịch vụ tạm thời không phản hồi. Vui lòng thử lại sau ít phút.</span><button className="primary-button" type="button" onClick={reset}>Thử lại</button></section>;
}
