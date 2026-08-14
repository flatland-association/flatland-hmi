import { TestBed } from '@angular/core/testing'
import { provideHttpClient } from '@angular/common/http'
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing'

import { DataService, Agent } from './data.service'

describe('DataService', () => {
  let service: DataService
  let httpMock: HttpTestingController

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    })
    service = TestBed.inject(DataService)
    httpMock = TestBed.inject(HttpTestingController)
  })

  afterEach(() => {
    httpMock.verify()
  })

  it('fetches agent plans for a trajectory from the agent_plans endpoint', async () => {
    const mockAgent: Agent = { handle: 0, position: [1, 2], direction: 0, moving: true, target: [3, 4], malfunction: 0 }
    const mockPlans: Array<Array<Record<string, Agent>>> = [[{ '0': mockAgent }, {}]]

    const promise = service.getTrajectoryAgentPlans('traj-1')

    const req = httpMock.expectOne('http://localhost:8000/trajectories/traj-1/agent_plans')
    expect(req.request.method).toBe('GET')
    req.flush(mockPlans)

    await expectAsync(promise).toBeResolvedTo(mockPlans)
  })
})
