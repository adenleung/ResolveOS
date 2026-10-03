import { Workbench } from "@/components/workbench";
export default async function Page({params, searchParams}: {params: Promise<{view?: string[]}>; searchParams: Promise<{case?: string; q?: string}>}) {
  const [{view = []}, search] = await Promise.all([params, searchParams]);
  return <Workbench view={view[0] ?? "overview"} caseId={view[1] ?? search.case ?? ""} query={search.q ?? ""} />;
}
