import fenics as fe
import numpy as np


Bc = None

class InitialConditions_ns(fe.UserExpression):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)  

    def eval(self, values, x):
        values[0] = 0.0  # Initial x-component of velocity
        values[1] = 0.0  # Initial y-component of velocity
        values[2] = 0.0  # Initial pressure

    def value_shape(self):
        return (3,)

def define_variables_ns(mesh):

    # Define finite elements for velocity, pressure, and temperature
    P1 = fe.VectorElement("Lagrange", mesh.ufl_cell(), 2)  # Velocity
    P2 = fe.FiniteElement("Lagrange", mesh.ufl_cell(), 1)  # Pressure 

    viscosity_func_space = fe.FunctionSpace(mesh, P2)
    phi_prev_interpolated_on_ns_mesh = fe.Function(viscosity_func_space)
    u_prev_interpolated_on_ns_mesh = fe.Function(viscosity_func_space)

    # Define mixed elements
    element = fe.MixedElement([P1, P2])

    # Create a function space
    function_space_ns = fe.FunctionSpace(mesh, element)

    # Define test functions
    test_1, test_2 = fe.TestFunctions(function_space_ns)

    # Define current and previous solutions
    solution_vector_ns = fe.Function(function_space_ns)  # Current solution
    solution_vector_ns_0 = fe.Function(function_space_ns)  # Previous solution

    # Split functions to access individual components
    u_answer, p_answer = fe.split(solution_vector_ns)  # Current solution
    u_prev, p_prev = fe.split(solution_vector_ns_0)  # Previous solution


       # Collapse function spaces to individual subspaces
    num_subs = function_space_ns.num_sub_spaces()
    spaces_ns, maps = [], []
    for i in range(num_subs):
        space_i, map_i = function_space_ns.sub(i).collapse(collapsed_dofs=True)
        spaces_ns.append(space_i)
        maps.append(map_i)

    return {
        'u_answer': u_answer, 'u_prev': u_prev,
        'p_answer': p_answer, 'p_prev': p_prev,
        'solution_vector_ns': solution_vector_ns, 'solution_vector_ns_0': solution_vector_ns_0,
        'test_1': test_1, 'test_2': test_2,
        'spaces_ns': spaces_ns, 'function_space_ns': function_space_ns,
        "phi_prev_interpolated_on_ns_mesh": phi_prev_interpolated_on_ns_mesh,
        "u_prev_interpolated_on_ns_mesh": u_prev_interpolated_on_ns_mesh, "viscosity_func_space": viscosity_func_space
    }


def epsilon(u):  

    return 0.5 * (fe.grad(u) + fe.grad(u).T)

def sigma(u, p):

    return 2  * epsilon(u) - p * fe.Identity(len(u))


def F1(variables_dict, physical_parameters_dict):

    # dt = physical_parameters_dict['dt']
    dt = physical_parameters_dict["dt"]
    test_2 = variables_dict['test_2']
    u_answer = variables_dict['u_answer']

    f1 = fe.inner(fe.div(u_answer)/dt, test_2)  * fe.dx

    return f1

def F2(variables_dict, physical_parameters_dict):

    # thermo-physical properties:
    W0_scale = physical_parameters_dict['W0_scale']
    tau_0_scale = physical_parameters_dict['tau_0_scale']
    mu_fluid = physical_parameters_dict['mu_fluid'](tau_0_scale, W0_scale)
    gravity = physical_parameters_dict['gravity'](tau_0_scale, W0_scale)
    alpha_c = physical_parameters_dict['alpha_c']
    viscosity_solid = physical_parameters_dict['viscosity_solid'](mu_fluid)
    viscosity_liquid = physical_parameters_dict['viscosity_liquid'](mu_fluid)
    rho_liquid = physical_parameters_dict["rho_liquid"]
    rho_solid = physical_parameters_dict["rho_solid"]
    k_eq = physical_parameters_dict['k_eq']
    opk = physical_parameters_dict['opk'](k_eq)
    omk = physical_parameters_dict['omk'](k_eq)
    # dt = physical_parameters_dict['dt']
    dt = physical_parameters_dict["dt"]
    u_answer = variables_dict['u_answer']
    u_prev = variables_dict['u_prev']
    p_answer = variables_dict['p_answer']
    test_1 = variables_dict['test_1']
    phi = variables_dict['phi_prev_interpolated_on_ns_mesh']
    U = variables_dict['u_prev_interpolated_on_ns_mesh']
    c_initial = physical_parameters_dict['c_initial']
    ######################## Coeff of boyancy ########################
    e_u = U * omk + 1 
    ter_1 = opk - omk * phi
    conctreation = c_initial * e_u / 2 * ter_1
    SN = (1 - phi) / 2 
    SP = (1 + phi) / 2
    Coeff1_Bou_NS = SN * alpha_c * gravity * (conctreation - c_initial)
    Coeff2_Bou_NS = SP * (rho_solid - rho_liquid) / rho_liquid * gravity
    ##########
    dy_mu_article = ( viscosity_solid/ rho_solid )* (1 + phi)/2 + ( viscosity_liquid/rho_liquid ) * (1 - phi)/2 # depends on range of Phi
    dy_mu = viscosity_liquid/rho_liquid ########## changed 
    beta = 1E12  # Large penalization parameter
    # penalization_term = beta *  (1 + phi)/2   * u_answer
    # threshold = 0.99  # Threshold close to 1 for activation
    threshold = 0.98  # Threshold close to 1 for activation
    penalization_term = fe.conditional(phi >= threshold, beta * (1 + phi) / 2 , 0)* u_answer

    # F2 = (
    #     fe.inner((u_answer - u_prev) / dt, test_1) * fe.dx
    #     + fe.inner(fe.dot(u_answer, fe.grad(u_answer)), test_1) * fe.dx
    #     + dy_mu * fe.inner(sigma(u_answer, p_answer), epsilon(test_1)) * fe.dx
    #     + fe.inner(penalization_term, test_1) * fe.dx  # Penalization term subtracted
    #     - fe.inner( Coeff1_Bou_NS , test_1[1] ) * fe.dx
    #     - fe.inner( Coeff2_Bou_NS , test_1[1] ) * fe.dx

    # )

    F2 = (
    fe.inner((u_answer - u_prev) / dt, test_1) * fe.dx
    + fe.inner(fe.dot(u_answer, fe.grad(u_answer)), test_1) * fe.dx
    + dy_mu_article * fe.inner(sigma(u_answer, p_answer), epsilon(test_1)) * fe.dx
    - fe.inner( Coeff1_Bou_NS , test_1[1] ) * fe.dx
    - fe.inner( Coeff2_Bou_NS , test_1[1] ) * fe.dx

    )
    return F2

def define_boundary_condition_ns(variables_dict, physical_parameters_dict) :

    global Bc

    Nx = physical_parameters_dict['Nx']
    Ny = physical_parameters_dict['Ny']
    Domain = physical_parameters_dict['Domain'](Nx, Ny)
    lid_vel_x = physical_parameters_dict['lid_vel_x']
    lid_vel_y = physical_parameters_dict['lid_vel_y']
    W = variables_dict['function_space_ns']

    # Define the Domain boundaries based on the previous setup
    (X0, Y0), (X1, Y1) = Domain

    # Define boundary conditions for velocity, pressure, and temperature
    class LeftBoundary(fe.SubDomain):
        def inside(self, x, on_boundary):
            return on_boundary and fe.near(x[0], X0)

    class RightBoundary(fe.SubDomain):
        def inside(self, x, on_boundary):
            return on_boundary and fe.near(x[0], X1)

    class BottomBoundary(fe.SubDomain):
        def inside(self, x, on_boundary):
            return on_boundary and fe.near(x[1], Y0)

    class TopBoundary(fe.SubDomain):
        def inside(self, x, on_boundary):
            return on_boundary and fe.near(x[1], Y1)

    # Instantiate boundary classes
    left_boundary = LeftBoundary()
    right_boundary = RightBoundary()
    bottom_boundary = BottomBoundary()
    top_boundary = TopBoundary()

    # Define Dirichlet boundary conditions
    bc_u_left = fe.DirichletBC(W.sub(0), fe.Constant((0, 0)), left_boundary)
    bc_u_right = fe.DirichletBC(W.sub(0), fe.Constant((0, 0)), right_boundary)
    bc_u_top_x = fe.DirichletBC(W.sub(0).sub(0), fe.Constant(lid_vel_x), top_boundary)
    bc_u_top_y = fe.DirichletBC(W.sub(0).sub(1), fe.Constant(lid_vel_y), top_boundary)
    bc_p_bottom = fe.DirichletBC(W.sub(1), fe.Constant(0.0), bottom_boundary)

    # Point for setting pressure
    zero_pressure_point = fe.Point( (X0)/2,  (Y1)/2 )
    bc_p_zero = fe.DirichletBC(W.sub(1), fe.Constant(0.0), lambda x, on_boundary: fe.near(x[0], zero_pressure_point.x()) and fe.near(x[1], zero_pressure_point.y()), method="pointwise")
    # Combine all boundary conditions


    # Bc = [bc_u_left, bc_u_right, bc_u_top_x, bc_u_top_y, bc_p_bottom]
    Bc = [bc_u_left, bc_u_right, bc_u_top_x, bc_u_top_y, bc_p_zero]


    return  Bc

def define_problem_ns(L, variables_dict, physical_parameters_dict):

    global Bc  


    solution_vector_ns = variables_dict['solution_vector_ns']

    abs_tol_ns = physical_parameters_dict["abs_tol_ns"]
    rel_tol_ns = physical_parameters_dict["rel_tol_ns"]
    linear_solver_ns = physical_parameters_dict['linear_solver_ns']
    nonlinear_solver_ns = physical_parameters_dict['nonlinear_solver_ns']
    preconditioner_ns = physical_parameters_dict['preconditioner_ns']
    maximum_iterations_ns = physical_parameters_dict['maximum_iterations_ns']

    J = fe.derivative(L, solution_vector_ns)
    problem_ns = fe.NonlinearVariationalProblem(L, solution_vector_ns, Bc, J)
    solver_ns = fe.NonlinearVariationalSolver(problem_ns)

    solver_parameters = {
        'nonlinear_solver': nonlinear_solver_ns,
        'snes_solver': {
            'linear_solver': linear_solver_ns,
            'report': False,
            "preconditioner": preconditioner_ns,
            'error_on_nonconvergence': False,
            'absolute_tolerance': abs_tol_ns,
            'relative_tolerance': rel_tol_ns,
            'maximum_iterations': maximum_iterations_ns,
        }
    }


    solver_ns.parameters.update(solver_parameters)

    return solver_ns

def update_solver_on_new_mesh_ns(mesh, physical_parameters_dict, old_solution_vector_ns= None, old_solution_vector_0_ns=None, 
                                old_solution_vector_0_pf=None, variables_dict= None):
    
    global Bc
    
    # define new solver after mesh refinement: 
    if old_solution_vector_ns is not None and old_solution_vector_0_ns is not None and old_solution_vector_0_pf is not None:

        variables_dict = define_variables_ns(mesh)

        solution_vector_ns = variables_dict['solution_vector_ns']
        solution_vector_ns_0 = variables_dict['solution_vector_ns_0']
        phi_prev_interpolated_on_ns_mesh = variables_dict['phi_prev_interpolated_on_ns_mesh']
        u_prev_interpolated_on_ns_mesh = variables_dict['u_prev_interpolated_on_ns_mesh']
        function_space_ns = variables_dict['function_space_ns']
        space_ns = variables_dict["spaces_ns"]

        # interpolate initial condition  after mesh refinement:
        fe.LagrangeInterpolator.interpolate(solution_vector_ns, old_solution_vector_ns)
        fe.LagrangeInterpolator.interpolate(solution_vector_ns_0, old_solution_vector_0_ns)

        # define the new boundary condition after mesh refinement:
        Bc = define_boundary_condition_ns(variables_dict, physical_parameters_dict)

        # gettting the old solution vector for the phase field and concentration field on ns mesh:
        phi_prev, u_prev = old_solution_vector_0_pf.split(deepcopy=True)
        fe.LagrangeInterpolator.interpolate(phi_prev_interpolated_on_ns_mesh , phi_prev)
        fe.LagrangeInterpolator.interpolate(u_prev_interpolated_on_ns_mesh , u_prev)


        # define the new forms after mesh refinement:
        f1_form = F1(variables_dict, physical_parameters_dict)
        f2_form = F2(variables_dict, physical_parameters_dict)

        # Define solver: 
        L= f1_form + f2_form
        solver_ns= define_problem_ns(L, variables_dict, physical_parameters_dict)

        return { 
            'solver_ns': solver_ns, 'solution_vector_ns': solution_vector_ns, 'solution_vector_ns_0': solution_vector_ns_0,
            "phi_prev_interpolated_on_ns_mesh": phi_prev_interpolated_on_ns_mesh,
            "u_prev_interpolated_on_ns_mesh": u_prev_interpolated_on_ns_mesh, "space_ns": space_ns,
            "Bc": Bc, "variables_dict": variables_dict, "function_space_ns": function_space_ns
        }

    # define the initial condition for the first time step:
    if old_solution_vector_ns is None and old_solution_vector_0_ns is  None and old_solution_vector_0_pf is  None and variables_dict is None: 

        variables_dict = define_variables_ns(mesh)
        solution_vector_ns = variables_dict['solution_vector_ns']
        solution_vector_ns_0 = variables_dict['solution_vector_ns_0']
        phi_prev_interpolated_on_ns_mesh = variables_dict['phi_prev_interpolated_on_ns_mesh']
        u_prev_interpolated_on_ns_mesh = variables_dict['u_prev_interpolated_on_ns_mesh']
        space_ns = variables_dict['spaces_ns']
        function_space_ns = variables_dict['function_space_ns']

        # interpolate initial condition  after mesh refinement:
        initial_conditions = InitialConditions_ns()
        solution_vector_ns_0.interpolate(initial_conditions)
        solution_vector_ns.interpolate(initial_conditions)

        # define the new boundary condition after mesh refinement:
        Bc = define_boundary_condition_ns(variables_dict, physical_parameters_dict)


        # define the new forms after mesh refinement:
        f1_form = F1(variables_dict, physical_parameters_dict)
        f2_form = F2(variables_dict, physical_parameters_dict)

        # Define solver: 
        L= f1_form + f2_form
        solver_ns= define_problem_ns(L, variables_dict, physical_parameters_dict)

        return { 
            'solver_ns': solver_ns, 'solution_vector_ns': solution_vector_ns, 'solution_vector_ns_0': solution_vector_ns_0,
            "space_ns": space_ns, "Bc": Bc, "variables_dict": variables_dict,
            "function_space_ns": function_space_ns
        }


    #updating: 
    if variables_dict is not None:


        phi_prev_interpolated_on_ns_mesh = variables_dict['phi_prev_interpolated_on_ns_mesh']
        u_prev_interpolated_on_ns_mesh = variables_dict['u_prev_interpolated_on_ns_mesh']
        space_ns = variables_dict['spaces_ns']
        function_space_ns = variables_dict['function_space_ns']

        # gettting the old solution vector for the phase field and concentration field on ns mesh:
        phi_prev, u_prev = old_solution_vector_0_pf.split(deepcopy=True)
        fe.LagrangeInterpolator.interpolate(phi_prev_interpolated_on_ns_mesh , phi_prev)
        fe.LagrangeInterpolator.interpolate(u_prev_interpolated_on_ns_mesh , u_prev)

        # define boundary condition:
        Bc = define_boundary_condition_ns(variables_dict, physical_parameters_dict)


        # define the new forms after mesh refinement:
        f1_form = F1(variables_dict, physical_parameters_dict)
        f2_form = F2(variables_dict, physical_parameters_dict)

        # Define solver: 
        L= f1_form + f2_form
        solver_ns= define_problem_ns(L, variables_dict, physical_parameters_dict)

        return { 
            "variables_dict": variables_dict, "solver_ns": solver_ns,
            "phi_prev_interpolated_on_ns_mesh": phi_prev_interpolated_on_ns_mesh, "u_prev_interpolated_on_ns_mesh": u_prev_interpolated_on_ns_mesh,
            "space_ns": space_ns, "Bc": Bc,
            "function_space_ns": function_space_ns
        }
















