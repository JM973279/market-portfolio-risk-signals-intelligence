import { notFound } from "next/navigation";
import DashboardView from "@/components/dashboard-view";
import { views, type View } from "@/lib/dashboard-types";
export function generateStaticParams() { return views.map(view => ({view})); }
export default async function ResearchPage({params}: {params: Promise<{view:string}>}) {
 const {view} = await params;
 if (!views.some(item => item === view)) notFound();
 return <DashboardView view={view as View}/>;
}
