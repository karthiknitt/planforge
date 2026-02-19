"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useSession } from "@/lib/auth-client";

const DIRECTIONS = ["N", "S", "E", "W"] as const;

export default function NewProjectPage() {
  const router = useRouter();
  const { data: session } = useSession();

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const [form, setForm] = useState({
    name: "",
    plot_length: "",
    plot_width: "",
    setback_front: "1.5",
    setback_rear: "1.5",
    setback_left: "1.0",
    setback_right: "1.0",
    road_side: "N",
    north_direction: "N",
    bhk: "2",
    toilets: "2",
    parking: false,
  });

  function set(field: string, value: string | boolean) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/projects`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": session!.user.id,
        },
        body: JSON.stringify({
          ...form,
          plot_length: parseFloat(form.plot_length),
          plot_width: parseFloat(form.plot_width),
          setback_front: parseFloat(form.setback_front),
          setback_rear: parseFloat(form.setback_rear),
          setback_left: parseFloat(form.setback_left),
          setback_right: parseFloat(form.setback_right),
          bhk: parseInt(form.bhk),
          toilets: parseInt(form.toilets),
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail ?? "Failed to create project.");
      }

      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <Card>
        <CardHeader>
          <CardTitle>New project</CardTitle>
          <CardDescription>Enter your plot details to generate floor plan options.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-6">

            {/* Project name */}
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="name">Project name</Label>
              <Input
                id="name"
                placeholder="My House — Trichy"
                required
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
              />
            </div>

            {/* Plot dimensions */}
            <fieldset className="flex flex-col gap-3">
              <legend className="text-sm font-medium">Plot dimensions (metres)</legend>
              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="plot_length">Length</Label>
                  <Input
                    id="plot_length"
                    type="number"
                    min="3"
                    step="0.1"
                    placeholder="12.0"
                    required
                    value={form.plot_length}
                    onChange={(e) => set("plot_length", e.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="plot_width">Width</Label>
                  <Input
                    id="plot_width"
                    type="number"
                    min="3"
                    step="0.1"
                    placeholder="9.0"
                    required
                    value={form.plot_width}
                    onChange={(e) => set("plot_width", e.target.value)}
                  />
                </div>
              </div>
            </fieldset>

            {/* Setbacks */}
            <fieldset className="flex flex-col gap-3">
              <legend className="text-sm font-medium">Setbacks (metres)</legend>
              <div className="grid grid-cols-2 gap-4">
                {(["front", "rear", "left", "right"] as const).map((side) => (
                  <div key={side} className="flex flex-col gap-1.5">
                    <Label htmlFor={`setback_${side}`} className="capitalize">{side}</Label>
                    <Input
                      id={`setback_${side}`}
                      type="number"
                      min="0"
                      step="0.1"
                      required
                      value={form[`setback_${side}`]}
                      onChange={(e) => set(`setback_${side}`, e.target.value)}
                    />
                  </div>
                ))}
              </div>
            </fieldset>

            {/* Orientation */}
            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="road_side">Road facing</Label>
                <Select id="road_side" value={form.road_side} onChange={(e) => set("road_side", e.target.value)}>
                  {DIRECTIONS.map((d) => <option key={d} value={d}>{d}</option>)}
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="north_direction">North direction</Label>
                <Select id="north_direction" value={form.north_direction} onChange={(e) => set("north_direction", e.target.value)}>
                  {DIRECTIONS.map((d) => <option key={d} value={d}>{d}</option>)}
                </Select>
              </div>
            </div>

            {/* Configuration */}
            <div className="grid grid-cols-3 gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="bhk">BHK</Label>
                <Select id="bhk" value={form.bhk} onChange={(e) => set("bhk", e.target.value)}>
                  <option value="2">2 BHK</option>
                  <option value="3">3 BHK</option>
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="toilets">Toilets</Label>
                <Select id="toilets" value={form.toilets} onChange={(e) => set("toilets", e.target.value)}>
                  {[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n}</option>)}
                </Select>
              </div>
              <div className="flex flex-col items-start justify-end gap-1.5 pb-1">
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="size-4 rounded"
                    checked={form.parking}
                    onChange={(e) => set("parking", e.target.checked)}
                  />
                  Parking
                </label>
              </div>
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex gap-3 pt-2">
              <Button type="submit" disabled={loading || !session}>
                {loading ? "Saving…" : "Create project"}
              </Button>
              <Button type="button" variant="outline" onClick={() => router.push("/dashboard")}>
                Cancel
              </Button>
            </div>

          </form>
        </CardContent>
      </Card>
    </div>
  );
}
