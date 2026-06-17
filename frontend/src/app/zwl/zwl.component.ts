import { Component, OnInit } from '@angular/core'
import { StateService } from '../state.service'
import { MapCell, RendererService } from '../renderer.service'
import { firstValueFrom } from 'rxjs'
import { Agent, DataService } from '../data.service'
import { FormsModule } from '@angular/forms'
import {TrainCoordinate} from '../marey/marey.component';
import { ControllerService, State } from '../controller.service'

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
  public reverseMapping: Record<string, [number, number]> = {}

  constructor(
    public stateService: StateService,
    public rendererService: RendererService,
    private dataService: DataService,
    public controllerService: ControllerService,
  ) {}

  ngOnInit() {
    this.stateService.getTransitions().subscribe(() => this.fetchAgentTransitions())
    this.stateService.getCurrentAgent().subscribe((currentAgent) => {
      this.currentAgent = currentAgent
      this.fetchAgentTransitions()
    })

    this.stateService.getAgents().subscribe((agents) => {
      this.agents = agents
      this.agentOptions = agents.map(a => ({ value: String(a.handle), label: `Agent ${a.handle}` }))
      if (!this.agentOptions.find(o => o.value === this.currentAgent)) {
        this.currentAgent = this.agentOptions[0]?.value ?? ''
      }
    })
  }

  private setMapping(mapping: Record<string, unknown>) {
    this.mapping = mapping
    this.reverseMapping = {}
    for (const [key, val] of Object.entries(mapping)) {
      if (Array.isArray(val) && val.length >= 2) {
        const match = key.match(/\((\d+), (\d+)\)/)
        if (match) {
          this.reverseMapping[`(${val[0]}, ${val[1]})`] = [parseInt(match[1]), parseInt(match[2])]
        }
      }
    }
  }

  public getOriginalPosition(zwlRow: number, zwlCol: number): [number, number] | null {
    return this.reverseMapping[`(${zwlRow}, ${zwlCol})`] ?? null
  }

  public getZwlPosition(x:number, y: number) {
    const key = `(${x}, ${y})`
    const val = this.mapping[key]
    console.log(`   ${key} --> ${val}   : ${this.mapping}`)
    if (Array.isArray(val) && val.length >= 2) {
      return [val[0] as number, val[1] as number]
    }
    return null
  }

  public onAgentChange() {
    this.stateService.setCurrentAgent(this.currentAgent)
  }

  private fetchAgentTransitions() {
    const trajectoryId = this.stateService.getTrajectoryId()
    if (!trajectoryId || !this.currentAgent) return
    this.dataService.getTrajectoryAgentTransitions(trajectoryId, this.currentAgent)
      .then(data =>
        firstValueFrom(this.stateService.getAgents()).then(agents => {
          this.mapClasses = this.rendererService.renderMap(data.grid, agents)
          this.setMapping(data.mapping)
        })
      )
  }
}
