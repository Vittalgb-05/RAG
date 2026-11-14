"use client";

import React, { useState } from "react";
import {
  ShieldAlert,
  ShieldCheck,
  Cpu,
  Key,
  HardDrive,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
} from "lucide-react";
import { toast } from "sonner";
import {
  useRevokeCloudCredentials,
  useSettings,
  useTelemetry,
  useUpdateCloudSettings,
} from "@/lib/api/queries";
import { SpotlightCard } from "@/components/motion/spotlight-card";
import { cn } from "@/lib/utils";

const CLOUD_PROVIDERS = [
  { id: "groq", name: "Groq Cloud" },
  { id: "openai", name: "OpenAI" },
  { id: "anthropic", name: "Anthropic" },
];

const CLOUD_MODELS: Record<string, string[]> = {
  groq: ["groq/llama-3.3-70b-versatile", "groq/mixtral-8x7b-32768"],
  openai: ["openai/gpt-4o", "openai/gpt-4o-mini"],
  anthropic: ["anthropic/claude-3-5-haiku-20241022", "anthropic/claude-3-5-sonnet-20241022"],
};

export default function SettingsPage() {
  const { data: settings } = useSettings();
  const { data: telemetry } = useTelemetry();
  const updateCloud = useUpdateCloudSettings();
  const revokeKeys = useRevokeCloudCredentials();

  const [provider, setProvider] = useState<string>("groq");
  const [model, setModel] = useState<string>("groq/llama-3.3-70b-versatile");
  const [apiKey, setApiKey] = useState("");
  const [consentChecked, setConsentChecked] = useState(false);
  const [consentModalOpen, setConsentModalOpen] = useState(false);

  const isCloud = settings?.cloud.enabled;

  const handleToggleCloud = (enable: boolean) => {
    if (enable) {
      setConsentModalOpen(true);
    } else {
      updateCloud.mutate(
        {
          enabled: false,
          provider: settings?.cloud.provider || "groq",
          model: settings?.cloud.model || "groq/llama-3.3-70b-versatile",
          consent: false,
        },
        {
          onSuccess: () => toast.success("Reverted to local inference engine"),
        }
      );
    }
  };

  const handleConfirmConsent = () => {
    if (!consentChecked) {
      toast.error("You must explicitly grant cloud data transmission consent");
      return;
    }

    updateCloud.mutate(
      {
        enabled: true,
        provider,
        model,
        consent: true,
        api_key: apiKey || undefined,
      },
      {
        onSuccess: () => {
          toast.success("Cloud inference enabled successfully");
          setConsentModalOpen(false);
          setApiKey("");
        },
        onError: (err: any) => {
          toast.error(err.message || "Cloud transition failed");
        },
      }
    );
  };

  const handleRevokeKeys = () => {
    revokeKeys.mutate(undefined, {
      onSuccess: () => toast.success("Revoked all cloud credentials and reverted to local"),
    });
  };

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-8">
      {/* Banner if Cloud Active */}
      {isCloud && (
        <div className="p-4 rounded-[14px] bg-[#FBBF24]/10 border border-[#FBBF24]/30 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-[#FBBF24] shrink-0" />
            <div>
              <h4 className="text-sm font-semibold text-[#FBBF24]">Cloud Egress Permitted</h4>
              <p className="text-xs text-[#A1A1AA]">
                Document snippets are currently routed through external LLM provider APIs.
              </p>
            </div>
          </div>
          <button
            onClick={() => handleToggleCloud(false)}
            className="px-3 py-1.5 rounded-lg bg-[#FBBF24] text-black font-semibold text-xs hover:opacity-90"
          >
            Revert to Local
          </button>
        </div>
      )}

      {/* Section: Inference Mode */}
      <SpotlightCard className="p-6 space-y-6">
        <div className="flex items-center justify-between border-b border-[rgba(255,255,255,0.08)] pb-4">
          <div>
            <h3 className="text-base font-bold text-[#F4F4F5]">Inference Engine</h3>
            <p className="text-xs text-[#A1A1AA]">
              Toggle between strict local on-device inference and high-capacity cloud models.
            </p>
          </div>

          <div className="flex items-center gap-2 bg-[#14141B] p-1 rounded-lg border border-[rgba(255,255,255,0.08)]">
            <button
              onClick={() => handleToggleCloud(false)}
              className={cn(
                "px-3 py-1.5 rounded-md text-xs font-semibold transition-all",
                !isCloud
                  ? "bg-[#34D399] text-black shadow"
                  : "text-[#A1A1AA] hover:text-[#F4F4F5]"
              )}
            >
              Local Engine
            </button>
            <button
              onClick={() => handleToggleCloud(true)}
              className={cn(
                "px-3 py-1.5 rounded-md text-xs font-semibold transition-all",
                isCloud
                  ? "bg-[#FBBF24] text-black shadow"
                  : "text-[#A1A1AA] hover:text-[#F4F4F5]"
              )}
            >
              Cloud Provider
            </button>
          </div>
        </div>

        {/* Cloud Config options */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="text-xs font-semibold text-[#A1A1AA]">Target Provider</label>
            <select
              value={provider}
              onChange={(e) => {
                setProvider(e.target.value);
                setModel(CLOUD_MODELS[e.target.value][0]);
              }}
              className="w-full px-3 py-2 rounded-lg bg-[#14141B] border border-[rgba(255,255,255,0.08)] text-xs text-[#F4F4F5] outline-none"
            >
              {CLOUD_PROVIDERS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <label className="text-xs font-semibold text-[#A1A1AA]">Model Identifier</label>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-[#14141B] border border-[rgba(255,255,255,0.08)] text-xs text-[#F4F4F5] outline-none"
            >
              {(CLOUD_MODELS[provider] || []).map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2 md:col-span-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-[#A1A1AA]">API Key</label>
              {settings?.cloud.has_key && (
                <span className="text-[11px] text-[#34D399] font-medium flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> Key Stored in Memory
                </span>
              )}
            </div>
            <div className="flex items-center gap-3">
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={settings?.cloud.has_key ? "••••••••••••••••••••" : "Paste API key"}
                className="flex-1 px-3 py-2 rounded-lg bg-[#14141B] border border-[rgba(255,255,255,0.08)] text-xs text-[#F4F4F5] outline-none"
              />
              <button
                onClick={handleRevokeKeys}
                className="px-3 py-2 rounded-lg border border-[#F87171]/30 text-[#F87171] hover:bg-[#F87171]/10 text-xs font-semibold flex items-center gap-1.5 transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Revoke Keys</span>
              </button>
            </div>
          </div>
        </div>
      </SpotlightCard>

      {/* Section: Resource Gauges */}
      <SpotlightCard className="p-6 space-y-4">
        <h3 className="text-base font-bold text-[#F4F4F5]">Resource Telemetry</h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {telemetry?.gpu && (
            <div className="p-4 rounded-lg bg-[#14141B] border border-[rgba(255,255,255,0.06)] space-y-2">
              <div className="flex justify-between text-xs">
                <span className="text-[#A1A1AA] flex items-center gap-1.5">
                  <Cpu className="w-4 h-4 text-[#A78BFA]" /> GPU VRAM
                </span>
                <span className="font-mono text-[#F4F4F5]">
                  {Math.round(telemetry.gpu.used_mb)} / {Math.round(telemetry.gpu.total_mb)} MB
                </span>
              </div>
              <div className="w-full h-2 rounded-full bg-[rgba(255,255,255,0.08)] overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-[#A78BFA] to-[#22D3EE]"
                  style={{
                    width: `${Math.round((telemetry.gpu.used_mb / telemetry.gpu.total_mb) * 100)}%`,
                  }}
                />
              </div>
            </div>
          )}

          {telemetry?.process && (
            <div className="p-4 rounded-lg bg-[#14141B] border border-[rgba(255,255,255,0.06)] space-y-2">
              <div className="flex justify-between text-xs">
                <span className="text-[#A1A1AA] flex items-center gap-1.5">
                  <HardDrive className="w-4 h-4 text-[#22D3EE]" /> Process RAM
                </span>
                <span className="font-mono text-[#F4F4F5]">
                  {Math.round(telemetry.process.rss_mb)} MB (RSS)
                </span>
              </div>
              <div className="w-full h-2 rounded-full bg-[rgba(255,255,255,0.08)] overflow-hidden">
                <div
                  className="h-full bg-[#22D3EE]"
                  style={{
                    width: `${Math.min(100, Math.round((telemetry.process.rss_mb / 4096) * 100))}%`,
                  }}
                />
              </div>
            </div>
          )}
        </div>
      </SpotlightCard>

      {/* Cloud Consent Modal */}
      {consentModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-[14px] bg-[#14141B] border border-[rgba(255,255,255,0.12)] p-6 space-y-5 shadow-2xl">
            <div className="flex items-center gap-3 text-[#FBBF24]">
              <ShieldAlert className="w-6 h-6 shrink-0" />
              <h3 className="font-bold text-base text-[#F4F4F5]">Cloud Transmission Consent</h3>
            </div>

            <p className="text-xs text-[#A1A1AA] leading-relaxed">
              Enabling cloud inference routes retrieved excerpts from your documents to external LLM provider endpoints ({provider}). Your raw documents remain strictly local, but answers and evidence context will traverse external networks.
            </p>

            <label className="flex items-start gap-2.5 cursor-pointer select-none text-xs text-[#F4F4F5]">
              <input
                type="checkbox"
                checked={consentChecked}
                onChange={(e) => setConsentChecked(e.target.checked)}
                className="mt-0.5 rounded border-white/20 bg-[#0C0C11] text-[#A78BFA] focus:ring-0"
              />
              <span>I understand and consent to transmitting query context to {provider}.</span>
            </label>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setConsentModalOpen(false)}
                className="px-4 py-2 rounded-lg text-xs text-[#A1A1AA] hover:text-[#F4F4F5]"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmConsent}
                disabled={!consentChecked}
                className="px-4 py-2 rounded-lg bg-gradient-to-r from-[#A78BFA] to-[#22D3EE] text-black font-semibold text-xs hover:opacity-90 disabled:opacity-40 transition-opacity"
              >
                Accept & Enable Cloud
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
