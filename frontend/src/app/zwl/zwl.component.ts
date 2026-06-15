import { Component, OnInit } from '@angular/core'
import { StateService } from '../state.service'
import { MapCell, RendererService } from '../renderer.service'
import { firstValueFrom } from 'rxjs'
import { Agent, DataService } from '../data.service'
import { FormsModule } from '@angular/forms'
import {TrainCoordinate} from '../marey/marey.component';

interface SelectOption {
  value: string
  label: string
}

@Component({
  selector: 'app-zwl',
  imports: [FormsModule],
  templateUrl: './zwl.component.html',
  styleUrl: './zwl.component.scss',
})
export class ZwlComponent implements OnInit {
  public mapClasses: Array<Array<MapCell>> = []
  public agents: Array<Agent> = []

  public agentOptions: SelectOption[] = []
  public currentAgent = ''
  public mapping: Record<string, unknown> = {}

  constructor(
    public stateService: StateService,
    public rendererService: RendererService,
    private dataService: DataService,
  ) {}

  ngOnInit() {
    this.stateService.getTransitions().subscribe(() => this.fetchAgentTransitions())
    this.stateService.getCurrentAgent().subscribe((agent) => {
      this.currentAgent = agent
    })

    this.stateService.getAgents().subscribe((agents) => {
      this.agents = agents
      this.agentOptions = agents.map(a => ({ value: String(a.handle), label: `Agent ${a.handle}` }))
      if (!this.agentOptions.find(o => o.value === this.currentAgent)) {
        this.currentAgent = this.agentOptions[0]?.value ?? ''
      }
    })
  }

  public getZwlPosition(coord: TrainCoordinate, i: string): [number, number] | null {
    const key = `(${coord.x}, ${coord.y})`
    const val = this.mapping[key]
    if (Array.isArray(val) && val.length >= 2) {
      return [val[0] as number, val[1] as number]
    }
    return null
  }

  public onAgentChange() {

    this.fetchAgentTransitions()
    this.stateService.setCurrentAgent(this.currentAgent)
  }

  private fetchAgentTransitions() {
    const trajectoryId = this.stateService.getTrajectoryId()
    if (!trajectoryId || !this.currentAgent) return
    this.dataService.getTrajectoryAgentTransitions(trajectoryId, this.currentAgent)
      .then(transitions =>
        firstValueFrom(this.stateService.getAgents()).then(agents => {
          this.mapClasses = this.rendererService.renderMap(transitions.grid, agents)
        })
      )
  }
}
