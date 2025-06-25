import { Component, OnInit } from '@angular/core'
import { firstValueFrom } from 'rxjs'
import { StateService } from '../state.service'
import { MapCell, RendererService } from '../renderer.service'
import { Agent } from '../data.service'
import { ControllerService } from '../controller.service'

@Component({
  selector: 'app-map',
  imports: [],
  templateUrl: './map.component.html',
  styleUrl: './map.component.scss',
})
export class MapComponent implements OnInit {
  public mapClasses: Array<Array<MapCell>> = []
  public agents: Array<Agent> = []

  public plans: Array<Array<Record<string, Agent>>> = []
  public selectedPlan?: number

  public interrupted: boolean = false
  public hasMalfunction: boolean = false

  constructor(
    public stateService: StateService,
    public rendererService: RendererService,
    public controllerService: ControllerService,
  ) {}

  ngOnInit() {
    this.stateService.getPlan().subscribe((planIndex) => {
      this.selectedPlan = planIndex
    })
    this.stateService.getNewMalfunction().subscribe(() => {
      this.interrupted = true
    })
    this.stateService.getTransitions().subscribe((transitions) =>
      firstValueFrom(this.stateService.getAgents()).then((agents) => {
        this.mapClasses = this.rendererService.renderMap(transitions, agents)
      }),
    )
    this.stateService.getAgents().subscribe((agents) => {
      this.agents = agents
      this.hasMalfunction = agents.some((agent) => agent.malfunction > 0)
    })
    this.stateService.getPlans().subscribe((plans) => (this.plans = plans))
    this.controllerService.observeReset().subscribe(() => {
      this.interrupted = false
      this.selectedPlan = undefined
    })
  }

  public selectPlan(planIndex: number | undefined) {
    this.interrupted = false
    this.stateService.setPlan(planIndex)
    this.stateService.play()
  }
}
