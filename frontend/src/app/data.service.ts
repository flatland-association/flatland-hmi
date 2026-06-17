import { HttpClient } from '@angular/common/http'
import { Injectable } from '@angular/core'
import { firstValueFrom } from 'rxjs'

const BACKEND_URL = 'http://localhost:8000'

export type Transitions = Array<Array<number>>

export interface ZwlResponse {
  grid: Transitions
  mapping: Record<string, unknown>
}

export interface EnvOption {
  id: string
  description: string
}

export interface PolicyOption {
  id: string
  description: string
}

export interface StationsResponse {
  city_cells: Record<string, [number, number][]>
  outer_connection_points_per_city: Record<string, number[][]>
  inter_city_lines: Array<{
    start: [number, number]
    end: [number, number]
    city_from: number
    city_to: number
  }>
}

export interface Agent {
  handle: number
  position: [number, number] | null
  direction: number
  moving: boolean
  target: [number, number]
  malfunction: number
}

@Injectable({
  providedIn: 'root',
})
export class DataService {
  constructor(private http: HttpClient) {}

  public getTrajectoryTransitions(trajectoryId: string) {
    return firstValueFrom(
      this.http.get<Transitions>(`${BACKEND_URL}/trajectories/${trajectoryId}/transitions`),
    )
  }

  public getTrajectoryAgentTransitions(trajectoryId: string, agentId: string) {
    return firstValueFrom(
      this.http.get<ZwlResponse>(`${BACKEND_URL}/trajectories/${trajectoryId}/zwl/${agentId}`),
    )
  }

  public getTrajectoryStations(trajectoryId: string) {
    return firstValueFrom(
      this.http.get<StationsResponse>(`${BACKEND_URL}/trajectories/${trajectoryId}/stations`),
    )
  }

  public getTrajectoryAgents(trajectoryId: string) {
    return firstValueFrom(
      this.http.get<Array<Agent>>(`${BACKEND_URL}/trajectories/${trajectoryId}/agents`),
    )
  }

  public getEnvs() {
    return firstValueFrom(this.http.get<Array<EnvOption>>(`${BACKEND_URL}/envs`))
  }

  public getPolicies() {
    return firstValueFrom(this.http.get<Array<PolicyOption>>(`${BACKEND_URL}/policies`))
  }
}
