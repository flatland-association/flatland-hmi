import { HttpClient } from '@angular/common/http'
import { Injectable } from '@angular/core'
import { firstValueFrom } from 'rxjs'

const BACKEND_URL = 'http://localhost:8000'

export interface State {
  steps: number
  done: {
    __all__: boolean
    [key: string]: boolean
  }
}

@Injectable({
  providedIn: 'root',
})
export class ControllerService {
  constructor(private http: HttpClient) {}

  public stepEnv() {
    return firstValueFrom(this.http.post<State>(`${BACKEND_URL}/step`, {}))
  }

  public resetEnv() {
    return firstValueFrom(this.http.post<State>(`${BACKEND_URL}/reset`, {}))
  }
}
