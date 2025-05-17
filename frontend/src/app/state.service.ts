import { Injectable } from '@angular/core'
import { DataService } from './data.service'
import { ReplaySubject } from 'rxjs'
import { ControllerService } from './controller.service'

@Injectable({
  providedIn: 'root',
})
export class StateService {
  private map = new ReplaySubject<any>(1)
  private agents = new ReplaySubject<any>(1)
  private interval?: number

  public get playing() {
    return this.interval !== undefined
  }

  constructor(
    private dataService: DataService,
    private controllerService: ControllerService,
  ) {
    this.dataService.getMap().then((map) => {
      this.map.next(map)
    })
    this.dataService.getAgents().then((agents) => {
      this.agents.next(agents)
    })
  }

  public getMap() {
    return this.map.asObservable()
  }

  public getAgents() {
    return this.agents.asObservable()
  }

  public next() {
    this.controllerService.stepEnv().then(() => {
      this.dataService.getMap().then((map) => {
        this.map.next(map)
      })
      this.dataService.getAgents().then((agents) => {
        this.agents.next(agents)
      })
    })
  }

  public reset() {
    this.controllerService.resetEnv().then(() => {
      this.dataService.getMap().then((map) => {
        this.map.next(map)
      })
      this.dataService.getAgents().then((agents) => {
        this.agents.next(agents)
      })
    })
  }

  public play() {
    this.interval = window.setInterval(() => {
      this.controllerService.stepEnv().then(() => {
        this.dataService.getMap().then((map) => {
          this.map.next(map)
        })
        this.dataService.getAgents().then((agents) => {
          this.agents.next(agents)
        })
      })
    }, 500)
  }

  public stop() {
    if (this.interval) {
      clearInterval(this.interval)
      this.interval = undefined
    }
  }

  
}
