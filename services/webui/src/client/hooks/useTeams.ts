/**
 * TanStack Query hook for fetching teams.
 */

import { useQuery } from "@tanstack/react-query";
import api from "../lib/api";

export interface Team {
  id?: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
}

const teamsKeys = {
  all: ["teams"] as const,
  list: () => ["teams", "list"] as const,
};

export function useTeams() {
  return useQuery({
    queryKey: teamsKeys.list(),
    queryFn: async () => {
      const response = await api.get<{ teams: Team[] }>("/teams");
      return response.data.teams;
    },
    staleTime: 5 * 60 * 1000,
  });
}
