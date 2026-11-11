// 화면 언어에 따른 시장 순서: KR 화면은 한국 → 미국, EN 화면은 미국 → 한국.
export type Market = "korea" | "us";

export function marketOrder(language: string): readonly Market[] {
 return language === "en" ? ["us", "korea"] : ["korea", "us"];
}
