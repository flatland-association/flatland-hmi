import { Component, OnInit } from '@angular/core'
import { StateService } from '../state.service'
import { MapCell, RendererService } from '../renderer.service'
import { firstValueFrom } from 'rxjs'
import { Agent, DataService } from '../data.service'
import { FormsModule } from '@angular/forms'

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

  constructor(
    public stateService: StateService,
    public rendererService: RendererService,
    private dataService: DataService,
  ) {}

  ngOnInit() {
    this.stateService.getTransitions().subscribe(() => this.fetchAgentTransitions())
    this.stateService.getAgents().subscribe((agents) => {
      this.agents = agents
      this.agentOptions = agents.map(a => ({ value: String(a.handle), label: `Agent ${a.handle}` }))
      if (!this.agentOptions.find(o => o.value === this.currentAgent)) {
        this.currentAgent = this.agentOptions[0]?.value ?? ''
      }
      this.fetchAgentTransitions()
    })
  }

  public onAgentChange() {
    this.fetchAgentTransitions()
  }

  private fetchAgentTransitions() {
    const trajectoryId = this.stateService.getTrajectoryId()
    if (!trajectoryId || !this.currentAgent) return
    this.dataService.getTrajectoryAgentTransitions(trajectoryId, this.currentAgent)
      .then(transitions =>
        firstValueFrom(this.stateService.getAgents()).then(agents => {
          this.mapClasses = this.rendererService.renderMap(transitions, agents)
        })
      )
  }
}
