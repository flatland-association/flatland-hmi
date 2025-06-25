import { Injectable } from '@angular/core'
import { Agent, DataService, Transitions } from './data.service'
import { BehaviorSubject, firstValueFrom, ReplaySubject, Subject } from 'rxjs'
import { ControllerService, State } from './controller.service'

@Injectable({
  providedIn: 'root',
})
export class StateService {
  private transitions = new ReplaySubject<Transitions>(1)
  private agents = new ReplaySubject<Array<Agent>>(1)
  private state = new ReplaySubject<State>(1)
  private interval?: number

  private plans = new Subject<Array<Array<Record<string, Agent>>>>()
  private history = new Subject<Array<Record<string, Agent>>>()
  private currentPolicyIndex = 0
  private selectedPlan = new BehaviorSubject<number | undefined>(undefined)

  private malfunctions: Record<number, boolean> = {}
  private newMalfunction = new Subject<void>()

  public get playing() {
    return this.interval !== undefined
  }

  constructor(
    private dataService: DataService,
    private controllerService: ControllerService,
  ) {
    this.dataService.getTransitions().then((transitions) => {
      this.transitions.next(transitions)
    })
    this.dataService.getHistory().then((history) => {
      this.history.next(history)
    })
  }

  public getNewMalfunction() {
    return this.newMalfunction.asObservable()
  }

  public setCurrentPolicyIndex(index: number) {
    this.currentPolicyIndex = index
  }

  public setPlan(planIndex: number | undefined) {
    this.selectedPlan.next(planIndex)
  }

  public getPlan() {
    return this.selectedPlan.asObservable()
  }

  public getPlans() {
    return this.plans.asObservable()
  }

  public getTransitions() {
    return this.transitions.asObservable()
  }

  public getAgents() {
    return this.agents.asObservable()
  }

  public getState() {
    return this.state.asObservable()
  }

  public next() {
    return this.controllerService.stepEnv(this.currentPolicyIndex).then((nextPolicyIndex) => {
      this.currentPolicyIndex = nextPolicyIndex
      return this.dataService.getPlans().then((plans) =>
        this.dataService.getHistory().then((history) => {
          const agents = Object.values(history[history.length - 1])
          this.agents.next(agents)
          this.plans.next(plans)
          this.history.next(history)

          const malfunctions = agents.reduce((acc: Record<number, boolean>, agent) => {
            acc[agent.direction] = agent.malfunction > 0
            return acc
          }, {})
          let newMalfunction = false
          for (const agentId in malfunctions) {
            if (malfunctions[agentId] && !this.malfunctions[agentId]) {
              newMalfunction = true
              break
            }
          }
          if (newMalfunction) {
            this.newMalfunction.next()
          }
          this.malfunctions = malfunctions
          return newMalfunction
        }),
      )
    })
  }

  public reset() {
    this.stop()
    this.controllerService.resetEnv().then((state) => {
      this.dataService.getTransitions().then((transitions) =>
        this.dataService.getHistory().then(() => {
          this.transitions.next(transitions)
          this.agents.next([])
        }),
      )
      this.state.next(state)
    })
  }

  public play() {
    this.next().then((newMalfunction) => {
      if (newMalfunction) {
        this.stop()
      } else {
        this.interval = window.setTimeout(() => {
          this.play()
        }, 500)
      }
    })
  }

  public stop() {
    if (this.interval) {
      clearTimeout(this.interval)
      this.interval = undefined
      this.malfunctions = {}
    }
  }

  public getHistory() {
    return this.history.asObservable()
  }
}
