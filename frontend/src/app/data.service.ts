import { HttpClient } from '@angular/common/http'
import { Injectable } from '@angular/core'
import { firstValueFrom } from 'rxjs'

const BACKEND_URL = 'http://localhost:8000'

export type Transitions = Array<Array<number>>

export interface EnvOption {
  id: string
  description: string
}

export interface PolicyOption {
  id: string
  description: string
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

  public getTransitions() {
    return firstValueFrom(
      this.http.get<Transitions>(`${BACKEND_URL}/transitions`),
    )
  }

  public getAgents() {
    return firstValueFrom(this.http.get<Array<Agent>>(`${BACKEND_URL}/agents`))
  }

  public getEnvs() {
    return firstValueFrom(this.http.get<Array<EnvOption>>(`${BACKEND_URL}/envs`))
  }

  public getPolicies() {
    return firstValueFrom(this.http.get<Array<PolicyOption>>(`${BACKEND_URL}/policies`))
  }
}
