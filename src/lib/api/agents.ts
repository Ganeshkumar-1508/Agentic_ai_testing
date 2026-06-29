import { api } from "./api-client";

export interface Agent {
  name: string;
  description: string;
  model: string | null;
  tools: string[];
  skills: string[];
  prompt: string;
}

export interface CreateAgentRequest {
  name: string;
  description?: string;
  model?: string | null;
  tools?: string[];
  skills?: string[];
  prompt?: string;
}

export async function listAgents(): Promise<Agent[]> {
  const data = await api.get<{ agents: Agent[] }>("/api/agents");
  return data.agents;
}

export async function getAgent(name: string): Promise<Agent> {
  return api.get<Agent>(`/api/agents/${encodeURIComponent(name)}`);
}

export async function createAgent(req: CreateAgentRequest): Promise<Agent> {
  return api.post<Agent>("/api/agents", req);
}

export async function updateAgent(name: string, req: CreateAgentRequest): Promise<Agent> {
  return api.put<Agent>(`/api/agents/${encodeURIComponent(name)}`, req);
}

export async function deleteAgent(name: string): Promise<void> {
  await api.delete(`/api/agents/${encodeURIComponent(name)}`);
}

export async function checkAgentName(
  name: string,
): Promise<{ available: boolean }> {
  return api.get<{ available: boolean }>("/api/agents/check", { name });
}
