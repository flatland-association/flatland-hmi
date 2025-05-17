import { HttpClient } from '@angular/common/http'
import { Injectable } from '@angular/core'
import { firstValueFrom } from 'rxjs'

const BACKEND_URL = 'http://localhost:8000'

@Injectable({
  providedIn: 'root',
})
export class DataService {
  constructor(private http: HttpClient) {}

  public getMap() {
    return firstValueFrom(this.http.get(`${BACKEND_URL}/map`))
  }

  public getAgents() {
    return firstValueFrom(this.http.get(`${BACKEND_URL}/agents`))
  }
}
