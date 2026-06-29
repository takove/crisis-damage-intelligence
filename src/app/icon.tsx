import { ImageResponse } from "next/og";
import { BrandIcon } from "@/app/_lib/brand-icon";

export const size = { width: 64, height: 64 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(<BrandIcon />, { ...size });
}
